import requests
import time

BASE_URL = "http://127.0.0.1:5000/whatsapp"
FROM_NUMBER = "whatsapp:+1999999999" # Different number to avoid old state

def test_location_first():
    print("--- Starting Location First Test ---")
    
    # 1. Send Location
    print("\n1. Sending Location...")
    payload_location = {
        "From": FROM_NUMBER,
        "Latitude": "12.9716",
        "Longitude": "77.5946"
    }
    
    try:
        r1 = requests.post(BASE_URL, data=payload_location)
        print(f"Status: {r1.status_code}")
        print(f"Response: {r1.text}")
        
        if "Location received" in r1.text:
            print("✅ STEP 1 SUCCESS: Location stored.")
        else:
            print("❌ STEP 1 FAILURE: Unexpected response.")
            
    except Exception as e:
         print(f"❌ Error connecting to server: {e}")

if __name__ == "__main__":
    test_location_first()
