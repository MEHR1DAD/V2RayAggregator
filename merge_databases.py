import sqlite3
import os
import argparse

def merge_databases(input_dir, output_db_path):
    """
    Merges data from multiple small SQLite databases into a single main database.
    It reads all configs from the source databases and upserts them into the target.
    """
    print("--- Starting Database Merge Process ---")
    
    # Ensure the output database and its tables exist
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
    db_files = [f for f in os.listdir(input_dir) if f.endswith('.db')]

    print(f"Found {len(db_files)} database files to merge in '{input_dir}'.")

    for db_file in db_files:
        source_db_path = os.path.join(input_dir, db_file)
        try:
            source_conn = sqlite3.connect(source_db_path)
            source_cursor = source_conn.cursor()
            
            # Fetch all configs from the source database
            source_cursor.execute("SELECT config, source_url, country_code, speed_kbps, last_tested FROM configs")
            configs_to_merge = source_cursor.fetchall()
            
            if configs_to_merge:
                # Use executemany for an efficient bulk upsert
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
                print(f"  -> Merged {len(configs_to_merge)} configs from {db_file}.")
                total_merged_configs += len(configs_to_merge)

            source_conn.close()
        except sqlite3.Error as e:
            print(f"  -> Error processing {db_file}: {e}")

    main_conn.close()
    print(f"\n--- Database merge finished. A total of {total_merged_configs} records were processed. ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge multiple SQLite databases from workers into one.")
    parser.add_argument('--input-dir', required=True, help="Directory containing the database files to merge.")
    parser.add_argument('--output-db', required=True, help="Path to the final, merged database file.")
    
    args = parser.parse_args()
    
    merge_databases(args.input_dir, args.output_db)