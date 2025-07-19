import sqlite3
import os
import argparse

def merge_databases(input_dir, output_db_path):
    """
    Merges data from multiple small SQLite databases into a single main database.
    It recursively finds all .db files in the input directory and upserts their data.
    """
    print("--- Starting Database Merge Process ---")
    
    main_conn = sqlite3.connect(output_db_path)
    main_cursor = main_conn.cursor()
    main_cursor.execute('''
        CREATE TABLE IF NOT EXISTS configs (
            config TEXT PRIMARY KEY,
            source_url TEXT,
            country_code TEXT,
            speed_kbps REAL,
            last_tested TEXT
        )
    ''')
    main_conn.commit()

    if not os.path.exists(input_dir):
        print(f"Input directory '{input_dir}' not found. No databases to merge.")
        main_conn.close()
        return

    total_merged_configs = 0
    db_files_paths = []
    
    # Recursively find all .db files in the input directory and subdirectories
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if file.endswith('.db'):
                db_files_paths.append(os.path.join(root, file))

    print(f"Found {len(db_files_paths)} database files to merge in '{input_dir}'.")

    for db_path in db_files_paths:
        try:
            source_conn = sqlite3.connect(db_path)
            source_cursor = source_conn.cursor()
            
            source_cursor.execute("SELECT config, source_url, country_code, speed_kbps, last_tested FROM configs")
            configs_to_merge = source_cursor.fetchall()
            
            if configs_to_merge:
                main_cursor.executemany('''
                    INSERT INTO configs (config, source_url, country_code, speed_kbps, last_tested)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(config) DO UPDATE SET
                        source_url = excluded.source_url,
                        country_code = excluded.country_code,
                        speed_kbps = excluded.speed_kbps,
                        last_tested = excluded.last_tested
                ''', configs_to_merge)
                main_conn.commit()
                print(f"  -> Merged {len(configs_to_merge)} configs from {os.path.basename(db_path)}.")
                total_merged_configs += len(configs_to_merge)

            source_conn.close()
        except sqlite3.Error as e:
            print(f"  -> Error processing {os.path.basename(db_path)}: {e}")

    main_conn.close()
    print(f"\n--- Database merge finished. A total of {total_merged_configs} records were processed. ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge multiple SQLite databases from workers into one.")
    parser.add_argument('--input-dir', required=True, help="Directory containing the database files to merge.")
    parser.add_argument('--output-db', required=True, help="Path to the final, merged database file.")
    
    args = parser.parse_args()
    
    merge_databases(args.input_dir, args.output_db)
