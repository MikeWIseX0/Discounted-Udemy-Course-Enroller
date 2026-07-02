import json
import sqlite3
import datetime
import threading
from loguru import logger
from duce.core.config import get_user_data_path


class DatabaseManager:
    CURRENT_VERSION = 1

    def __init__(self, db_filename="duce.db"):
        self.lock = threading.Lock()
        if db_filename == ":memory:":
            self.db_path = ":memory:"
        else:
            self.db_path = get_user_data_path(db_filename)
        logger.info(f"Initializing SQLite database at: {self.db_path}")

        # Backup path
        self.backup_path = self.db_path + ".bak" if db_filename != ":memory:" else None

        import os
        import shutil

        try:
            self._create_tables()
            # If successful, create a backup
            if self.backup_path:
                try:
                    shutil.copy2(self.db_path, self.backup_path)
                except Exception:
                    pass
        except sqlite3.DatabaseError as db_err:
            logger.error(f"Database corruption detected: {db_err}. Attempting recovery...")
            if self.backup_path and os.path.exists(self.backup_path):
                try:
                    if os.path.exists(self.db_path):
                        os.remove(self.db_path)
                    shutil.copy2(self.backup_path, self.db_path)
                    logger.info("Restored database from backup file.")
                    self._create_tables()
                    return
                except Exception as restore_err:
                    logger.error(f"Failed to restore database backup: {restore_err}")

            # Re-initialize from scratch
            logger.warning("Re-initializing database from scratch to resolve corruption.")
            try:
                if os.path.exists(self.db_path):
                    os.remove(self.db_path)
            except Exception:
                pass
            self._create_tables()

    def _get_connection(self):
        # Using a small timeout to prevent lock blocks during concurrent executions
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA cache_size=-2000")
        except Exception as e:
            logger.debug(f"Failed to set WAL/performance pragmas: {e}")
        return conn

    def _handle_db_error(self, e):
        import os
        import shutil
        logger.error(f"Database operation failed: {e}. Attempting auto-healing recovery...")
        if self.db_path == ":memory:":
            try:
                self._create_tables()
            except Exception as recreate_err:
                logger.error(f"Failed to auto-heal memory database: {recreate_err}")
            return

        try:
            if self.backup_path and os.path.exists(self.backup_path):
                logger.warning("Database auto-healing: attempting to restore from backup.")
                try:
                    if os.path.exists(self.db_path):
                        os.remove(self.db_path)
                    shutil.copy2(self.backup_path, self.db_path)
                    self._create_tables()
                    logger.info("Database successfully restored from backup during auto-healing.")
                    return
                except Exception as backup_err:
                    logger.error(f"Failed to restore backup during auto-healing: {backup_err}")
            
            # Clean recreation fallback
            logger.warning("Database auto-healing: recreating database from scratch.")
            try:
                if os.path.exists(self.db_path):
                    os.remove(self.db_path)
            except Exception:
                pass
            self._create_tables()
            logger.info("Database successfully recreated from scratch during auto-healing.")
        except Exception as heal_err:
            logger.critical(f"Database auto-healing completely failed: {heal_err}")

    def _create_tables(self):
        try:
            conn = self._get_connection()
            try:
                with conn:
                    cursor = conn.cursor()
                    # Subscribed/Enrolled courses table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS enrolled_courses (
                            slug TEXT PRIMARY KEY,
                            enrollment_time TEXT NOT NULL
                        )
                    """)
                    # Course details and validation cache
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS validation_cache (
                            slug TEXT,
                            coupon_code TEXT,
                            is_valid INTEGER,
                            is_excluded INTEGER,
                            is_free INTEGER,
                            error TEXT,
                            title TEXT,
                            course_id TEXT,
                            price TEXT,
                            instructors TEXT,
                            language TEXT,
                            category TEXT,
                            rating REAL,
                            last_update TEXT,
                            is_coupon_valid INTEGER,
                            cached_at TEXT,
                            PRIMARY KEY (slug, coupon_code)
                        )
                    """)
                    # Create index for fast lookups
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_validation_cache ON validation_cache (slug, coupon_code)")

                    # Sweep validation cache older than 7 days to prevent database bloat
                    try:
                        seven_days_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).isoformat()
                        cursor.execute("DELETE FROM validation_cache WHERE cached_at < ?", (seven_days_ago,))
                        logger.info("Swept expired validation cache entries from database")
                    except Exception as sweep_err:
                        logger.debug(f"Failed to sweep expired validation cache: {sweep_err}")
            finally:
                conn.close()

            self._initialize_schema_versioning()
        except Exception as e:
            logger.error(f"Failed to initialize database tables: {e}")

    def _initialize_schema_versioning(self):
        try:
            conn = self._get_connection()
            try:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS db_metadata (
                            key TEXT PRIMARY KEY,
                            value TEXT NOT NULL
                        )
                    """)
                    conn.commit()

                    # Get current version
                    cursor.execute(
                        "SELECT value FROM db_metadata WHERE key = 'schema_version'")
                    row = cursor.fetchone()
                    if row is None:
                        # Let's check if enrolled_courses already exists
                        cursor.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name='enrolled_courses'")
                        has_tables = cursor.fetchone() is not None

                        initial_version = 1 if not has_tables else 0
                        cursor.execute("INSERT INTO db_metadata (key, value) VALUES ('schema_version', ?)",
                                       (str(initial_version),))
                        db_version = initial_version
                    else:
                        db_version = int(row[0])
            finally:
                conn.close()

            logger.info(
                f"Database schema version: {db_version} (Latest: {self.CURRENT_VERSION})")
            if db_version < self.CURRENT_VERSION:
                self._run_migrations(db_version)
        except Exception as e:
            logger.error(f"Error during schema version checking: {e}")

    def _run_migrations(self, current_version):
        logger.info(
            f"Migrating database from version {current_version} to {self.CURRENT_VERSION}")
        try:
            conn = self._get_connection()
            try:
                with conn:
                    cursor = conn.cursor()
                    if current_version < 1:
                        # Example migration: baseline setup
                        pass

                    # Update schema version to CURRENT_VERSION
                    cursor.execute("INSERT OR REPLACE INTO db_metadata (key, value) VALUES ('schema_version', ?)",
                                   (str(self.CURRENT_VERSION),))
            finally:
                conn.close()
            logger.info(
                f"Database migrated to version {self.CURRENT_VERSION} successfully")
        except Exception as e:
            logger.error(f"Failed to execute database migrations: {e}")

    def save_enrolled_courses(self, courses_dict: dict[str, str]) -> None:
        """Save a dictionary of slug -> enrollment_time to the database"""
        if not courses_dict:
            return
        with self.lock:
            try:
                conn = self._get_connection()
                try:
                    with conn:
                        cursor = conn.cursor()
                        cursor.executemany(
                            "INSERT OR REPLACE INTO enrolled_courses (slug, enrollment_time) VALUES (?, ?)",
                            [(slug.lower(), time) for slug, time in courses_dict.items()]
                        )
                finally:
                    conn.close()
                logger.debug(
                    f"Saved {len(courses_dict)} enrolled courses to database")
            except Exception as e:
                self._handle_db_error(e)
                try:
                    conn = self._get_connection()
                    try:
                        with conn:
                            cursor = conn.cursor()
                            cursor.executemany(
                                "INSERT OR REPLACE INTO enrolled_courses (slug, enrollment_time) VALUES (?, ?)",
                                [(slug.lower(), time) for slug, time in courses_dict.items()]
                            )
                    finally:
                        conn.close()
                    logger.debug(
                        f"Saved {len(courses_dict)} enrolled courses after database auto-heal")
                except Exception as retry_e:
                    logger.error(f"Failed to save enrolled courses even after auto-heal retry: {retry_e}")

    def get_enrolled_courses(self) -> dict[str, str]:
        """Retrieve all enrolled courses from the database"""
        courses = {}
        with self.lock:
            try:
                conn = self._get_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT slug, enrollment_time FROM enrolled_courses")
                    for slug, time in cursor.fetchall():
                        courses[slug.lower()] = time
                finally:
                    conn.close()
            except Exception as e:
                self._handle_db_error(e)
                try:
                    conn = self._get_connection()
                    try:
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT slug, enrollment_time FROM enrolled_courses")
                        for slug, time in cursor.fetchall():
                            courses[slug.lower()] = time
                    finally:
                        conn.close()
                except Exception as retry_e:
                    logger.error(f"Failed to get enrolled courses even after auto-heal retry: {retry_e}")
        return courses

    def save_validation(self, course_obj: object) -> None:
        """Saves a Course object's validation state to the database cache"""
        if not course_obj or not course_obj.slug:
            return
        with self.lock:
            try:
                slug = course_obj.slug.lower()
                coupon_code = course_obj.coupon_code or ""
                is_valid = 1 if course_obj.is_valid else 0
                is_excluded = 1 if course_obj.is_excluded else 0
                is_free = 1 if course_obj.is_free else 0
                error = course_obj.error or ""
                title = course_obj.title or ""
                course_id = course_obj.course_id or ""
                price = str(
                    course_obj.price) if course_obj.price is not None else ""
                instructors = json.dumps(course_obj.instructors)
                language = course_obj.language or ""
                category = course_obj.category or ""
                rating = course_obj.rating if course_obj.rating is not None else -1.0
                last_update = course_obj.last_update or ""
                is_coupon_valid = 1 if course_obj.is_coupon_valid else 0
                cached_at = datetime.datetime.now(
                    datetime.timezone.utc).isoformat()

                conn = self._get_connection()
                try:
                    with conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT OR REPLACE INTO validation_cache (
                                slug, coupon_code, is_valid, is_excluded, is_free, error, title,
                                course_id, price, instructors, language, category, rating,
                                last_update, is_coupon_valid, cached_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            slug, coupon_code, is_valid, is_excluded, is_free, error, title,
                            course_id, price, instructors, language, category, rating,
                            last_update, is_coupon_valid, cached_at
                        ))
                finally:
                    conn.close()
                logger.debug(
                    f"Saved validation cache for course {slug} (coupon: {coupon_code})")
            except Exception as e:
                self._handle_db_error(e)
                try:
                    conn = self._get_connection()
                    try:
                        with conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT OR REPLACE INTO validation_cache (
                                    slug, coupon_code, is_valid, is_excluded, is_free, error, title,
                                    course_id, price, instructors, language, category, rating,
                                    last_update, is_coupon_valid, cached_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                slug, coupon_code, is_valid, is_excluded, is_free, error, title,
                                course_id, price, instructors, language, category, rating,
                                last_update, is_coupon_valid, cached_at
                            ))
                    finally:
                        conn.close()
                    logger.debug(
                        f"Saved validation cache for course {slug} after database auto-heal")
                except Exception as retry_e:
                    logger.error(
                        f"Failed to save validation cache even after auto-heal retry: {retry_e}")

    def get_validation(self, slug, coupon_code):
        """Retrieve a cached course validation state if it exists and is fresh (within 7 days)"""
        if not slug:
            return None
        slug = slug.lower()
        coupon_code = coupon_code or ""
        with self.lock:
            def _query_cache():
                conn = self._get_connection()
                try:
                    with conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT is_valid, is_excluded, is_free, error, title, course_id, price,
                                   instructors, language, category, rating, last_update, is_coupon_valid,
                                   cached_at
                            FROM validation_cache
                            WHERE slug = ? AND coupon_code = ?
                        """, (slug, coupon_code))
                        row = cursor.fetchone()
                        if row:
                            # Check cache freshness: 7 days max age
                            cached_at_str = row[13] if len(row) > 13 else None
                            if cached_at_str:
                                try:
                                    cached_at = datetime.datetime.fromisoformat(
                                        cached_at_str)
                                    age = datetime.datetime.now(
                                        datetime.timezone.utc) - cached_at
                                    if age.days > 7:
                                        logger.debug(
                                            f"Validation cache expired for {slug} (age: {age.days} days)")
                                        cursor.execute(
                                            "DELETE FROM validation_cache WHERE slug = ? AND coupon_code = ?",
                                            (slug, coupon_code)
                                        )
                                        return None
                                except (ValueError, TypeError) as e:
                                    logger.debug(
                                        f"Could not parse cached_at timestamp: {e}")
                            price_str = row[6]
                            try:
                                from decimal import Decimal
                                price_val = Decimal(
                                    price_str) if price_str else None
                            except Exception:
                                price_val = None

                            try:
                                instructors_val = json.loads(row[7])
                            except Exception:
                                instructors_val = []

                            return {
                                "is_valid": bool(row[0]),
                                "is_excluded": bool(row[1]),
                                "is_free": bool(row[2]),
                                "error": row[3] if row[3] else None,
                                "title": row[4],
                                "course_id": row[5] if row[5] else None,
                                "price": price_val,
                                "instructors": instructors_val,
                                "language": row[8] if row[8] else None,
                                "category": row[9] if row[9] else None,
                                "rating": row[10] if row[10] != -1.0 else None,
                                "last_update": row[11] if row[11] else None,
                                "is_coupon_valid": bool(row[12])
                            }
                finally:
                    conn.close()
                return None

            try:
                return _query_cache()
            except Exception as e:
                self._handle_db_error(e)
                try:
                    return _query_cache()
                except Exception as retry_e:
                    logger.error(f"Failed to query validation cache even after auto-heal retry: {retry_e}")
            return None


# Global instance
db = DatabaseManager()
