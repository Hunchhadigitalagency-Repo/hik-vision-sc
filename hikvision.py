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
                last_sync_date_time = datetime.strptime(last_sync_date_time, "%Y-%m-%dT%H:%M:%S+05:45").strftime("%Y-%m-%dT%H:%M:%S+05:45")
            except ValueError:
                logging.error("Invalid date format for last_sync_date_time")
                return None
        else:
            last_sync_date_time = last_sync_date_time.strftime("%Y-%m-%dT%H:%M:%S+05:45")
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
        response = requests.post(url, json=payload, auth=requests.auth.HTTPDigestAuth(username, password))
        response.raise_for_status()
        data = response.json()
        filtered_events = [
            event for event in data.get("AcsEvent", {}).get("InfoList", [])
            if event.get("major") == 5 and event.get("minor") == 38
        ]
        grouped_data = groupByFilteredData(filtered_events)
        return grouped_data
    except requests.exceptions.RequestException as e:
        logging.error(f"An error occurred during the request: {str(e)}")
        return None

def sendGroupedDataToServer(grouped_data, server_endpoint):
    try:
        response = requests.post(server_endpoint, json=grouped_data)
        response.raise_for_status()
        logging.info("Data sent to server successfully")

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
    
def sendLogFileDataToserver():
    server_endpoint = "https://manish.vatvateyriders.com/api/device/store-log-file-data/"
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
    
    # Send the log file data to the server
    try:
        response = requests.post(server_endpoint, data={'log_file': log_data})
        response.raise_for_status()
        logging.info("Log file data sent to server successfully")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending log file data to server: {str(e)}")
    
    # Clear the log file
    try:
        with open(log_file_path, 'w') as file:
            pass
        logging.info("Log file cleared successfully")
    except IOError as e:
        logging.error(f"Error clearing log file: {str(e)}")

def main():
    api_url = "https://manish.vatvateyriders.com/api/device/get-devices/all/"
    devices = fetchDeviceDataFromAPI(api_url)
    server_endpoint = "https://manish.vatvateyriders.com/api/device/post-device-data"
    while True:
        try:
            for device in devices:
                ip_address = device["device_ip"]
                username = device["device_user_name"]
                password = device["device_password"]
                last_sync_date_time = loadLastSyncDate()
                logging.info(f"Last sync date: {last_sync_date_time}")
                grouped_data = fetchDataFromDevice(ip_address, username, password, last_sync_date_time)
                if grouped_data:
                    logging.info(f"Grouped data: {ip_address},{grouped_data}")
                    sendGroupedDataToServer(grouped_data, server_endpoint)
                    saveDataToJson(grouped_data, "fetched_data.json")
                    saveLastSyncDate(datetime.now())
                    # sendLogFileDataToserver()
        except Exception as e:
            logging.error(f"An unexpected error occurred: {str(e)}")
        time.sleep(60)  # Sleep for 60 seconds before the next iteration

if __name__ == "__main__":
    main()
