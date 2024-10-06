import requests
from datetime import datetime, timedelta
from collections import defaultdict
import time
import json
import logging

# Configure logging
logging.basicConfig(filename='script.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def loadLastSyncDate():
    try:
        with open("last_sync_date.json", "r") as file:
            data = json.load(file)
            return datetime.strptime(data["last_sync_date"], "%Y-%m-%dT%H:%M:%S+05:45")
    except (FileNotFoundError, json.JSONDecodeError):
        logging.error("File not found or JSON decode error in last_sync_date.json")
        return datetime.now() - timedelta(days=1)  # Default to 1 day ago if file doesn't exist or is corrupted

def saveLastSyncDate():
    current_time = datetime.now()
    rounded_time = current_time.replace(minute=0, second=0, microsecond=0)  # Round down to the nearest hour

    # Load the last sync date to check if it has changed
    last_sync_date = loadLastSyncDate()

    # Only save the new time if it's a different hour
    if last_sync_date.hour != rounded_time.hour or last_sync_date.date() != rounded_time.date():
        with open("last_sync_date.json", "w") as file:
            json.dump({"last_sync_date": rounded_time.strftime("%Y-%m-%dT%H:%M:%S+05:45")}, file)
        logging.info(f"Last sync date updated to: {rounded_time.strftime('%Y-%m-%dT%H:%M:%S+05:45')}")

def groupByFilteredData(data):
    grouped_data = defaultdict(lambda: defaultdict(list))
    for event in data:
        event_date = event["time"][:10]  # Extract the date part of the time string
        employee_no = event.get("employeeNoString")
        if employee_no:
            grouped_data[event_date][employee_no].append(event)
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
        if isinstance(last_sync_date_time, str):
            try:
                last_sync_date_time = datetime.strptime(last_sync_date_time, "%Y-%m-%dT%H:%M:%S+05:45")
            except ValueError:
                logging.error("Invalid date format for last_sync_date_time")
                return None
        else:
            last_sync_date_time = last_sync_date_time

        today = datetime.now()
        end_time = today  # Current time as end_time

        all_grouped_data = []

        # Loop in 1-hour increments from last_sync_date_time to end_time
        current_start_time = last_sync_date_time
        while current_start_time < end_time:
            current_end_time = min(current_start_time + timedelta(hours=1), end_time)

            # Format times as required
            start_time_str = current_start_time.strftime("%Y-%m-%dT%H:%M:%S+05:45")
            end_time_str = current_end_time.strftime("%Y-%m-%dT%H:%M:%S+05:45")

            # List of payloads to iterate over
            payloads = [
                {
                    "AcsEventCond": {
                        "searchID": "0",
                        "searchResultPosition": 0,
                        "major": 0,
                        "minor": 0,
                        "maxResults": 1000,  # Adjusted to a reasonable value
                        "startTime": start_time_str,
                        "endTime": end_time_str,
                        "eventAttribute": "attendance"
                    }
                },
                {
                    "AcsEventCond": {
                        "searchID": "0",
                        "searchResultPosition": 0,
                        "major": 5,
                        "minor": 38,
                        "maxResults": 1000,
                        "startTime": start_time_str,
                        "endTime": end_time_str,
                        "eventAttribute": "attendance"
                    }
                },
                {
                    "AcsEventCond": {
                        "searchID": "0",
                        "searchResultPosition": 0,
                        "major": 5,
                        "minor": 39,
                        "maxResults": 1000,
                        "startTime": start_time_str,
                        "endTime": end_time_str,
                        "eventAttribute": "attendance"
                    }
                },
                {
                    "AcsEventCond": {
                        "searchID": "0",
                        "searchResultPosition": 0,
                        "major": 5,
                        "minor": 75,
                        "maxResults": 1000,
                        "startTime": start_time_str,
                        "endTime": end_time_str,
                        "eventAttribute": "attendance"
                    }
                }
            ]

            for payload in payloads:
                response = requests.post(url, json=payload, auth=requests.auth.HTTPDigestAuth(username, password))
                response.raise_for_status()
                data = response.json()

                filtered_events = [
                    event for event in data.get("AcsEvent", {}).get("InfoList", [])
                    if event.get("major") == 5
                ]
                grouped_data = groupByFilteredData(filtered_events)
                all_grouped_data.append(grouped_data)

            # Move to the next hour
            current_start_time = current_end_time

        return all_grouped_data

    except requests.exceptions.RequestException as e:
        logging.error(f"An error occurred during the request: {str(e)}")
        return None

def sendGroupedDataToServer(grouped_data, server_endpoint, organization_id):
    try:
        # Include the organization ID in the payload
        payload = {
            "organization_id": organization_id,
            "data": grouped_data
        }
        print(payload)
        # Send the request to the server
        response = requests.post(server_endpoint, json=payload)
        response.raise_for_status()  # Raise an exception for bad responses

        # Log the server's response content
        try:
            server_response_data = response.json()  # If the response is in JSON format
            logging.info(f"Data sent to server successfully. Server response: {server_response_data}")
        except ValueError:
            # If the response is not JSON, log the raw text
            logging.info(f"Data sent to server successfully. Server response: {response.text}")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending data to server: {str(e)}")

def saveDataToJson(data, filename):
    try:
        with open(filename, "w") as file:
            json.dump(data, file, indent=4)
        logging.info(f"Data saved to {filename}")
    except Exception as e:
        logging.error(f"Error saving data to {filename}: {str(e)}")

def fetchDeviceDataFromAPI(api_url):
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        devices = response.json()
        return devices
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching device data from API: {str(e)}")
        return []
    
def sendLogFileDataToserver(ip_address):
    server_endpoint = "https://gorakha.hajirkhata.com/api/log/log-entries/"
    log_file_path = 'script.log'
    # Read the log file
    try:
        with open(log_file_path, 'r') as file:
            log_data = file.read()
    except FileNotFoundError:
        logging.error("Log file not found")
        return
    except IOError as e:
        logging.error(f"Error reading log file: {str(e)}")
        return
    
    # Prepare data to send
    payload = {
        'log_text': log_data,
        'device_ip': ip_address
    }
    
    # Send the log file data to the server
    try:
        response = requests.post(server_endpoint, json=payload)
        response.raise_for_status()
        logging.info("Log file data sent to server successfully")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending log file data to server: {str(e)}")
    
    # Clear the log file
    try:
        open(log_file_path, 'w').close()
        logging.info("Log file cleared successfully")
    except IOError as e:
        logging.error(f"Error clearing log file: {str(e)}")

def main():
    api_url = "https://gorakha.hajirkhata.com/api/device/get-devices/all/"
    devices = fetchDeviceDataFromAPI(api_url)
    server_endpoint = "https://gorakha.hajirkhata.com/api/device/post-device-data"
    while True:
        try:
            for device in devices:
                ip_address = device["device_ip"]
                username = device["device_user_name"]
                password = device["device_password"]
                organization_id = device["organization"]
                last_sync_date_time = loadLastSyncDate()
                logging.info(f"Last sync date: {last_sync_date_time}")
                grouped_data = fetchDataFromDevice(ip_address, username, password, last_sync_date_time)
                if grouped_data:
                    logging.info(f"Grouped data fetched from: {ip_address},{grouped_data}")
                    sendGroupedDataToServer(grouped_data, server_endpoint, organization_id)
                    saveDataToJson(grouped_data, "fetched_data.json")
                    saveLastSyncDate()
                    sendLogFileDataToserver(ip_address)

        except Exception as e:
            logging.error(f"An unexpected error occurred: {str(e)}")
        time.sleep(60)  # Sleep for 60 seconds before the next iteration

if __name__ == "__main__":
    main()