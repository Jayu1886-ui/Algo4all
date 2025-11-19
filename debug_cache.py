import json
from app import create_app, cache

def run_debug():
    app, _ = create_app()
    hist_cache_key = "historical_data:NSE_INDEX|Nifty 50"

    with app.app_context():
        cached_json_data = cache.get(hist_cache_key)
        
        if cached_json_data:
            # The data is a JSON string of a list of dictionaries
            data_list = json.loads(cached_json_data)
            
            print(f"\n--- Retrieved {len(data_list)} Historical Candles ---")
            
            # Print the first 5 records
            for i, record in enumerate(data_list):
                if i >= 5:
                    break
                print(record)
            
            print("\n--- Data retrieval complete ---")
        else:
            print("Cache key not found.")

if __name__ == '__main__':
    run_debug()