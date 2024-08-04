import requests
from datetime import datetime, timedelta
from collections import defaultdict
import time
import json

def loadLastSyncDate():
    try:
        with open("last_sync_date.json", "r") as file:
            data = json.load(file)
            return datetime.strptime(data["last_sync_date"], "%Y-%m-%dT%H:%M:%S+05:45")
    except (FileNotFoundError, json.JSONDecodeError):
        return datetime.now() - timedelta(days=1)  # Default to 1 day ago if file doesn't exist or is corrupted
    
def saveLastSyncDate(last_sync_date):
    # Extract the date and set the time to 00:00:00
    start_of_day = datetime(last_sync_date.year, last_sync_date.month, last_sync_date.day, 0, 0, 0)
    # Format the datetime object to the desired string format with +05:45 timezone offset
    formatted_date = start_of_day.strftime("%Y-%m-%dT00:00:00+05:45")
    data = {"last_sync_date": formatted_date}
    
    # Save to JSON file
    with open("last_sync_date.json", "w") as file:
        json.dump(data, file)

def groupByFilteredData(data):
    # Group the attendance data first by date and then by 'employeeNoString'
    grouped_data = defaultdict(lambda: defaultdict(list))
    for event in data:
        event_date = event["time"][:10]  # Extract the date part of the time string
        employee_no = event.get("employeeNoString")
        if employee_no:
            grouped_data[event_date][employee_no].append(event)
    # For each employee on each date, keep only the first and last events
    filtered_grouped_data = {}
    for date, employees in grouped_data.items():
        filtered_grouped_data[date] = {}
        for employee_no, events in employees.items():
            if events:
                filtered_grouped_data[date][employee_no] = [events[0], events[-1]] if len(events) > 1 else events
    return filtered_grouped_data
def fetchDataFromDevice(ip_address, username, password, last_sync_date_time):
    url = f"http://{ip_address}/ISAPI/AccessControl/AcsEvent?format=json"
    try:
        # Ensure last_sync_date_time is in the correct format
        if isinstance(last_sync_date_time, str):
            try:
                # Parse and reformat to ensure correct format
                last_sync_date_time = datetime.strptime(last_sync_date_time, "%Y-%m-%dT%H:%M:%S+05:45").strftime("%Y-%m-%dT%H:%M:%S+05:45")
            except ValueError:
                print("Invalid date format for last_sync_date_time")
                return None
        else:
            last_sync_date_time = last_sync_date_time.strftime("%Y-%m-%dT%H:%M:%S+05:45")
        # Prepare payload for the request
        today = datetime.now()
        start_time = last_sync_date_time
        end_time = today.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%dT%H:%M:%S+05:45")
        payload = {
            "AcsEventCond": {
                "searchID": "1",
                "searchResultPosition": 0,
                "maxResults": 999999,
                "major": 5,
                "minor": 38,
                "startTime": start_time,
                "endTime": end_time,
                "eventAttribute": "attendance"
            }
        }
        # Make the request to the device API
        response = requests.post(url, json=payload, auth=requests.auth.HTTPDigestAuth(username, password))
        response.raise_for_status()
        data = response.json()
        # Filter events where major is 5 and minor is 38
        filtered_events = [
            event for event in data.get("AcsEvent", {}).get("InfoList", [])
            if event.get("major") == 5 and event.get("minor") == 38
        ]
        # Group and filter data
        grouped_data = groupByFilteredData(filtered_events)
        return grouped_data
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {str(e)}")
        return None
def sendGroupedDataToServer(grouped_data, server_endpoint):
    try:
        # Send data to server endpoint
        response = requests.post(server_endpoint, json=grouped_data)
        response.raise_for_status()
        print("Data sent successfully")
    except requests.exceptions.RequestException as e:
        print(f"Error sending data to server: {str(e)}")

def saveDataToJson(data, filename):
    try:
        with open(filename, "w") as file:
            json.dump(data, file, indent=4)
        print(f"Data saved to {filename}")
    except Exception as e:
        print(f"Error saving data to {filename}: {str(e)}")

def fetchDeviceDataFromAPI(api_url):
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        devices = response.json()  # Assuming the API returns JSON array of devices
        return devices
    except requests.exceptions.RequestException as e:
        print(f"Error fetching device data from API: {str(e)}")
        return []

def main():
    # Fetch devices from Django API
    api_url = "https://sujan.vatvateyriders.com/api/device/devices/"
    devices = fetchDeviceDataFromAPI(api_url)
    print(devices)

    server_endpoint = "https://sujan.vatvateyriders.com/api/device/post-device-data"
    while True:
        try:
            for device in devices:
                ip_address = device["device_ip"]
                username = device["device_user_name"]
                password = device["device_password"]
                # Load last sync date from file
                last_sync_date_time = loadLastSyncDate()
                print(last_sync_date_time)
                # Fetch data from the device
                grouped_data = fetchDataFromDevice(ip_address, username, password, last_sync_date_time)
                if grouped_data:
                    print(grouped_data,"yo ho")
                    # Send grouped data to server
                    sendGroupedDataToServer(grouped_data, server_endpoint)

                    saveDataToJson(grouped_data, "fetched_data.json")
                    # Update last sync date in file
                    saveLastSyncDate(datetime.now())
        except Exception as e:
            print(f"An error occurred: {str(e)}")
        # Sleep for 60 seconds before the next iteration
        time.sleep(3)
if __name__ == "__main__":
    main()