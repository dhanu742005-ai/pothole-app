import requests
import time

BASE_URL = "http://127.0.0.1:5000/whatsapp"
FROM_NUMBER = "whatsapp:+1234567890"
# Use a valid image URL that the server can download
IMAGE_URL = "https://raw.githubusercontent.com/ultralytics/yultralytics/main/ultralytics/assets/bus.jpg" 

def test_flow():
    print("--- Starting Webhook Flow Test ---")
    
    # 1. Send Image
    print("\n1. Sending Image...")
    payload_image = {
        "From": FROM_NUMBER,
        "MediaUrl0": IMAGE_URL
    }
    try:
        r1 = requests.post(BASE_URL, data=payload_image)
        print(f"Status: {r1.status_code}")
        print(f"Response: {r1.text}")
        
        if "Image received" not in r1.text:
            print("❌ FAILURE: Expected 'Image received' message.")
            return
    except Exception as e:
         print(f"❌ Error connecting to server: {e}")
         return

    time.sleep(1)

    # 2. Send Location
    print("\n2. Sending Location...")
    payload_location = {
        "From": FROM_NUMBER,
        "Latitude": "12.9716",
        "Longitude": "77.5946"
    }
    
    try:
        r2 = requests.post(BASE_URL, data=payload_location)
        print(f"Status: {r2.status_code}")
        print(f"Response: {r2.text}")
        
        if "Report received" in r2.text:
            print("\n✅ SUCCESS: Full flow completed successfully!")
        else:
            print("\n❌ FAILURE: Did not get success confirmation.")
            
    except Exception as e:
         print(f"❌ Error connecting to server: {e}")

if __name__ == "__main__":
    test_flow()
