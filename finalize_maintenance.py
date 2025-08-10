import sqlite3
import os
import argparse

def finalize_database(input_dir, final_db_path):
    """
    Finalizes the maintenance process by creating a new database from the
    successful re-test results and replacing the old one.
    This automatically prunes any configs that failed the re-test.
    """
    print("--- Starting Database Finalization Process ---")
    
    new_db_path = f"new_{final_db_path}"
    
    if os.path.exists(new_db_path):
        os.remove(new_db_path)

    # Create a new, clean database with the CORRECT schema
    main_conn = sqlite3.connect(new_db_path)
    main_cursor = main_conn.cursor()
    # *** FIX: Added the ping_ms column to the CREATE TABLE statement ***
    main_cursor.execute('''
        CREATE TABLE configs (
            config TEXT PRIMARY KEY,
            source_url TEXT,
            country_code TEXT,
            speed_kbps REAL,
            ping_ms INTEGER,
            last_tested TEXT
        )
    ''')
    main_conn.commit()

    if not os.path.exists(input_dir):
        print(f"Input directory '{input_dir}' not found. The new database will be empty.")
        main_conn.close()
        os.rename(new_db_path, final_db_path)
        return

    total_merged_configs = 0
    db_files_paths = [os.path.join(root, file) for root, _, files in os.walk(input_dir) for file in files if file.endswith('.db')]

    print(f"Found {len(db_files_paths)} result databases to merge.")

    for db_path in db_files_paths:
        try:
            source_conn = sqlite3.connect(db_path)
            source_cursor = source_conn.cursor()
            
            # *** FIX: Select the ping_ms column from partial results ***
            source_cursor.execute("SELECT config, source_url, country_code, speed_kbps, ping_ms, last_tested FROM configs")
            configs_to_merge = source_cursor.fetchall()
            
            if configs_to_merge:
                # *** FIX: Insert data including the ping_ms column ***
                main_cursor.executemany('''
                    INSERT INTO configs (config, source_url, country_code, speed_kbps, ping_ms, last_tested)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(config) DO UPDATE SET
                        speed_kbps = excluded.speed_kbps,
                        ping_ms = excluded.ping_ms,
                        last_tested = excluded.last_tested
                ''', configs_to_merge)
                main_conn.commit()
                print(f"  -> Merged {len(configs_to_merge)} configs from {os.path.basename(db_path)}.")
                total_merged_configs += len(configs_to_merge)

            source_conn.close()
        except sqlite3.Error as e:
            print(f"  -> Error processing {os.path.basename(db_path)}: {e}")

    main_conn.close()
    
    print(f"\nReplacing old database with the new one containing {total_merged_configs} live configs.")
    os.rename(new_db_path, final_db_path)
    
    print("--- Database finalization finished successfully. ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Finalize maintenance by rebuilding the database from partial results.")
    parser.add_argument('--input-dir', required=True, help="Directory containing the re-test result databases.")
    parser.add_argument('--output-db', required=True, help="Path to the final database file to be replaced.")
    
    args = parser.parse_args()
    
    finalize_database(args.input_dir, args.output_db)
