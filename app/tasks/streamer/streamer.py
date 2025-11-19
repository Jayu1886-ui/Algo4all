# streamer.py (FIXED VERSION)
import asyncio
import json
import ssl
import websockets
import requests
from google.protobuf.json_format import MessageToDict
from app.websocket.market_data_v3 import MarketDataFeedV3_pb2 as pb
from app.tasks._shutdown_manager import initialize_signal_handler, is_shutdown_requested
from app import cache 
import redis


redis_client = redis.Redis(host="127.0.0.1", port=6379, db=0)

initialize_signal_handler()


def get_market_data_feed_authorize_v3():
    """Get authorization for market data feed."""
    with open("access_token.txt", "r") as f:
        access_token = f.read().strip()

    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    url = 'https://api.upstox.com/v3/feed/market-data-feed/authorize'
    api_response = requests.get(url=url, headers=headers)
    api_response.raise_for_status()
    return api_response.json()


def decode_protobuf(buffer):
    """Decode protobuf message."""
    feed_response = pb.FeedResponse()
    feed_response.ParseFromString(buffer)
    return feed_response


async def fetch_market_data():
    """Fetch market data using WebSocket and store LTPs in cache."""

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    response = get_market_data_feed_authorize_v3()

    async with websockets.connect(response ["data"]["authorized_redirect_uri"], ssl=ssl_context) as websocket:
        print("✅ Connection established")

        # Subscribe to instrument
        data = {
            "guid": "someguid",
            "method": "sub",
            "data": {
                "mode": "ltpc",
                "instrumentKeys": ["NSE_INDEX|Nifty 50"]
            }
        }
        await websocket.send(json.dumps(data).encode("utf-8"))

        while not is_shutdown_requested():
            try:
                message = await websocket.recv()
                decoded_data = decode_protobuf(message)
                data_dict = MessageToDict(decoded_data)

                # ✅ Extract LTP if available
                feeds = data_dict.get("feeds", {})
                for instrument, info in feeds.items():
                    ltp = info.get("ltpc", {}).get("ltp")
                    if ltp:

                        payload_dict = {"ltp": str(ltp)}
                        payload_json_str = json.dumps(payload_dict)


                        cache_key = f"LTP:{instrument}"
                        # --- FIX: Use the defined variable payload_json_str ---
                        redis_client.setex(cache_key, 50, payload_json_str) 
                        
                        print(f"📈 Updated {cache_key} = {ltp}")

            except websockets.ConnectionClosed:
                print("⚠️ Connection closed, retrying...")
                await asyncio.sleep(2)
                return await fetch_market_data()
            except Exception as e:
                print(f"❌ Error in WebSocket loop: {e}")
                await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(fetch_market_data())
