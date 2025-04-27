#!/usr/bin/env python3

# Author: Manuel Ziel
# Date: 27-04-2025
# Version: 1.0.2
# License: MIT
#
# This programm is free software: you can redistribute it and/or modify
#
# Description:
# This script is used to update the DNS records of a domain on IONOS using the IONOS API.
# It fetches the current public IPv4 and IPv6 addresses and updates the DNS records if they have changed.
# Additionally, it ensures that the required DNS records (with and without "www.") are present.
# The script also supports activating Dynamic DNS (DynDNS) for the domain.
# 
# 
# Requirements:
# - Python 3.x
# 
# Usage:
# - Configure the script with your IONOS API credentials and domain information.
# - Run the script to automatically manage your DNS records.
# 
# See https://developer.hosting.ionos.de/docs/dns for more information.
# See https://github.com/manuelziel/dyndns for more information.

import threading
import requests
import json
from argparse import ArgumentParser, RawDescriptionHelpFormatter

import sys
import os
import time
import logging

# ANSI escape sequences for colors
RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"

# Custom formatter for colored logs
class ColoredFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.INFO:
            record.msg = f"{GREEN}{record.msg}{RESET}"
        elif record.levelno == logging.WARNING:
            record.msg = f"{YELLOW}{record.msg}{RESET}"
        elif record.levelno == logging.ERROR:
            record.msg = f"{RED}{record.msg}{RESET}"
        elif record.levelno == logging.DEBUG:
            record.msg = f"{BLUE}{record.msg}{RESET}"
        return super().format(record)
    
logging.basicConfig(stream=sys.stdout, format="%(asctime)s %(message)s", datefmt="%B %d %H:%M:%S", level=logging.INFO)
logger = logging.getLogger()
logger.handlers[0].setFormatter(ColoredFormatter())

help_link = "https://github.com/manuelziel/dyndns"

class NetworkData:
    def __init__(self, ipv4_address=None, ipv6_address=None, last_ipv4_address=None, last_ipv6_address=None):
        self.ipv4_address = ipv4_address
        self.ipv6_address = ipv6_address
        self.last_ipv4_address = last_ipv4_address
        self.last_ipv6_address = last_ipv6_address

        self.api_name = None
        self.api_bulkId = None
        self.api_key = None
        self.api_zone = None
        self.api_update_time = None

        self.api_setup = None

        self.api_url = "https://api.hosting.ionos.com/dns/v1/"
        self.api_headers = None

    def setup(self, api_name=None, api_bulkId=None, api_key=None, api_zone=None, api_update_time=None, api_url=None):
        if self.api_setup:
            return True
        else:
            
            if api_name and api_bulkId and api_key and api_zone and api_update_time:
                self.api_name = api_name
                self.api_bulkId = api_bulkId
                self.api_key = api_key
                self.api_zone = api_zone
                self.api_update_time = api_update_time

                self.api_headers = {
                    "accept": "*/*",
                    "X-API-Key": f"{self.api_bulkId}.{self.api_key}",
                    "Content-Type": "application/json"
                }
                logging.info(f"Loaded API information from environment variables:\n")
                logging.info(f"API Name set to: {self.api_name}")
                logging.info(f"API BulkId set")
                logging.info(f"API Key set")
                logging.info(f"Update Header with BulkId and Key")
                logging.info(f"API Zone set to: {self.api_zone}")
                logging.info(f"API Update Timeout set to: {self.api_update_time}\n")
                
            else :
                return False

            # override api_url if provided
            if api_url is not None:
                self.api_url = api_url
                logging.info(f"API URL set to: {self.api_url}\n")

            self.api_setup = True
            return True
    
    def get(self):
        return self

    def load_current_ip_address(self):
        self.ipv4_address = self.get_current_public_ipv4_address()
        self.ipv6_address = self.get_current_public_ipv6_address()
        return self.ipv4_address, self.ipv6_address

    def get_current_public_ipv4_address(self, retries=3, timeout=10):
        for attempt in range(retries):
            try:
                ipv4_address = requests.get("https://api.ipify.org", timeout=timeout).text
                if ipv4_address:
                    return ipv4_address
                else:
                    logging.warning("No ipv4 address found\n")
                    return None
            except requests.exceptions.Timeout:
                logging.warning(f"Attempt {attempt + 1}/{retries} to fetch ipv4 address failed")
            except requests.exceptions.RequestException as e:
                logging.warning(f"Error fetching ipv4 address (attempt {attempt + 1}/{retries})")
            time.sleep(2)
        logging.error("Failed to fetch ipv4 address after multiple attempts")
        return None

    def get_current_public_ipv6_address(self, retries=3, timeout=10):
        for attempt in range(retries):
            try:
                ipv6_address = requests.get("https://api6.ipify.org", timeout=timeout).text
                if ipv6_address:
                    return ipv6_address
                else:
                    logging.warning("No ipv6 address found\n")
                    return None
            except requests.exceptions.Timeout:
                logging.warning(f"Attempt {attempt + 1}/{retries} to fetch ipv6 address failed")
            except requests.exceptions.RequestException as e:
                logging.warning(f"Error fetching ipv6 address (attempt {attempt + 1}/{retries})")
            time.sleep(2)
        logging.error("Failed to fetch ipv6 address after multiple attempts")
        return None
        
    def save_ip_address(self):
        self.last_ipv4_address = self.ipv4_address
        self.last_ipv6_address = self.ipv6_address

class IONOSDynDNS:
    def __init__(self):
        logging.info("Starting IONOS DynDNS script...")
        self.api_name =  os.environ.get("IONOS_API_NAME")
        self.api_bulkId = os.environ.get("IONOS_API_BULKID")
        self.api_key = os.environ.get("IONOS_API_KEY")
        self.api_zone = os.environ.get("IONOS_API_ZONE")
        self.api_update_time = int(os.environ.get("IONOS_API_UPDATE_TIME", 5))

        if not all([self.api_name, self.api_bulkId, self.api_key, self.api_zone]):
            logging.error("Missing required environment variables. Please set IONOS_API_NAME, IONOS_API_BULKID, IONOS_API_KEY, and IONOS_API_ZONE.")
            logging.error(f"See {help_link} for more information.")
            logging.error(f"Current environment variables are: api_name: {self.api_name}, api_bulkId: {self.api_bulkId}, api_key: {self.api_key}, api_zone: {self.api_zone}, update_time: {self.api_update_time}")
            logging.error("Exiting...")
            sys.exit(1)
        
        self.network = NetworkData()

        self.zone = None
        self.target_a_record = None
        self.target_aaaa_record = None
        self.dynamic_dns = None

    def reset(self):
        self.save_zones(None, None)
        self.save_zone_informations(None)
        self.save_dynamic_dns(None)

    def request_zones(self, network=None):
        network_data = network
        api_url = network_data.api_url
        header = network_data.api_headers
        url = f"{api_url}/zones"
        return self.request_with_retry(method="GET", url=url, headers=header)

    def save_zones(self, api_zone=None, response=None):
        if response is not None and hasattr(response, 'text'):
            zones = json.loads(response.text)
            for zone in zones:
                if zone.get("name") == api_zone:
                    if self.set_zone(zone):
                        return True
                    else:
                        return None
                else:
                    self.set_zone(None)
                    return None
        else:
            self.set_zone(None)
            return None

    def set_zone(self, zone=None):
        self.zone = zone
        if zone is not None:
            return True
        else:
            return None

    def get_zone(self):
        if self.zone is not None:
            return self.zone
        else:
            return None
    
    def request_zone_information(self, network=None, zoneId=None):
        network_data = network
        api_url = network_data.api_url
        header = network_data.api_headers

        url = f"{api_url}/zones/{zoneId}"
        return self.request_with_retry(method="GET", url=url, headers=header)
    
    def save_zone_informations(self, response=None):
        if response and hasattr(response, 'text'):
            zone_information = json.loads(response.text)
            records = zone_information.get("records", [])

            a_records = []
            aaaa_records = []

            for record in records:
                if record.get("type") == "A":
                    a_records.append(record)
                elif record.get("type") == "AAAA":
                    aaaa_records.append(record)
                
            if self.set_zone_information(a_records, aaaa_records):
                return True
            else:
                return None
        else:
            self.set_zone_information(None, None)
            return None
        
    def set_zone_information(self, a_records=None, aaaa_records=None):
        self.target_a_record = a_records
        self.target_aaaa_record = aaaa_records

        if a_records is not None and aaaa_records is not None:
            return True
        else:
            return None

    def get_zone_information(self):
        if self.target_a_record is not None and self.target_aaaa_record is not None:
            return self.target_a_record, self.target_aaaa_record
        else:
            return None
        
    def update_record(self,network=None, zone_id=None, record=None, ip_address=None):
        json_data = None
        
        json_data = {
            "name": record.get("name"),
            "rootName": record.get("rootName"),
            "type": record.get("type"),
            "content": ip_address,
            "ttl": record.get("ttl"),
            "disabled": record.get("disabled"),
        }
        
        response = self.request_put_record_update(network, zone_id, record.get("id"), json_data)
        if response and hasattr(response, 'status_code'):
            if response.status_code == 200:
                return True
            elif response and hasattr(response, 'status_code') and response.status_code == "RECORD_NOT_FOUND":
                logging.warning(f"Record {record.get('type')} {record.get('name')} not found. Status code: {response.status_code}")
                return False
            else:
                logging.warning(f"Failed to update {record.get('type')} record {record.get('name')}: {response.status_code} {response.text}")
                return False
        else:
            logging.warning(f"Failed to update {record.get('type')} record {record.get('name')}: {response}")
            return None

    def request_put_record_update(self, network=None, target_zone=None, recordId=None, json_data=None):
        network_data = network
        api_url = network_data.api_url
        header = network_data.api_headers
        url = f"{api_url}/zones/{target_zone}/records/{recordId}"
        return self.request_with_retry(method="PUT", url=url, headers=header, json_data=json_data)

    def create_new_record(self, network=None, zone=None, type=None, ip_address=None, disabled=False):
        network_data = network
        ipv4_address = network_data.ipv4_address
        ipv6_address = network_data.ipv6_address
        if zone is not None and hasattr(zone, 'get'):
            if zone.get("name") is not None:
                ip_address = ipv4_address if type == "A" else ipv6_address if type == "AAAA" else None

                if ip_address is None:
                    logging.warning(f"Unsupported record: IP address could not be determined for type {type}")
                    return False

                json_data = [{
                    "name": zone.get("name"),
                    "rootName": zone.get("name"),
                    "type": type,
                    "content": ip_address,
                    "ttl": "3600",
                    "disabled": disabled,
                },
                {
                    "name": 'www.'+ zone.get("name"),
                    "rootName": zone.get("name"),
                    "type": type,
                    "content": ip_address,
                    "ttl": "3600",
                    "disabled": disabled,
                }]
                request = self.request_post_record(network, zone.get("id"), json_data)
                if request and hasattr(request, 'status_code') and hasattr(request, 'text'):
                    if request.status_code == 201:
                        return True
                    else:
                        logging.warning(f"Failed to create new record: {request.status_code} with {request.text}")
                        return False
                elif request and hasattr(request, 'status_code') and hasattr(request, 'text'):
                    logging.warning(f"Failed to create new record: {request.status_code} with {request.text}")
                    return False
                else:
                    logging.warning(f"Failed to create new record: {request} with {request.text}")
                    return False
            else:
                logging.warning(f"No zone.get('name') information found: {zone}")
                return False
        else:
            logging.warning(f"No zone.get information found: {zone}")
            return False
    
    def request_post_record(self, network=None, target_zone=None, json_data=None):
        network_data = network
        api_url = network_data.api_url
        header = network_data.api_headers

        url = f"{api_url}/zones/{target_zone}/records"
        return self.request_with_retry(method="POST", url=url, headers=header, json_data=json_data)
    
    def delete_record(self, network=None, zone=None, record=None):
        network_data = network
        api_url = network_data.api_url
        header = network_data.api_headers
        url = f"{api_url}/zones/{zone.get('id')}/records/{record.get('id')}"

        response = self.request_with_retry(method="DELETE", url=url, headers=header)
        if response and hasattr(response, 'status_code') and response.status_code == 200:
            return True
        else:
            logging.warning(f"Failed to delete record: {response})")
            return False
        
    def request_activate_dynamic_dns(self, network=None, json_data=None):
        network_data = network
        api_url = network_data.api_url
        header = network_data.api_headers

        url = f"{api_url}/dyndns"
        return self.request_with_retry(method="POST", url=url, headers=header, json_data=json_data)
    
    def save_dynamic_dns(self, response=None):
        if response and hasattr(response, 'text'):
            dynamic_dns = json.loads(response.text)
            if self.set_dynamic_dns(dynamic_dns):
                return True
            else:
                self.set_dynamic_dns(None)
                return None
        else:
            self.set_dynamic_dns(None)
            return None
    
    def set_dynamic_dns(self, dynamic_dns=None):
        self.dynamic_dns = dynamic_dns
        if dynamic_dns is not None:
            return True
        else:
            return None
        
    def get_dynamic_dns(self):
        if self.dynamic_dns:
            return self.dynamic_dns
        else:
            return None
    
    def request_with_retry(self, method=None, url=None, headers=None, json_data=None, retries=3, timeout=10):
        for attempt in range(retries):
            try:
                if method == "GET":
                    response = requests.get(url, headers=headers, timeout=timeout)
                elif method == "POST":
                    response = requests.post(url, headers=headers, json=json_data, timeout=timeout)
                elif method == "PUT":
                    response = requests.put(url, headers=headers, json=json_data, timeout=timeout)
                elif method == "DELETE":
                    response = requests.delete(url, headers=headers, timeout=timeout)
                else:
                    raise ValueError("Unsupported HTTP method!")
                return response
            except requests.exceptions.Timeout:
                logging.warning(f"Timeout while request (attempt {attempt + 1}/{retries}) Retrying...")
                time.sleep(2) 
            except requests.exceptions.RequestException as e:
                logging.warning(f"Request failed on (attempt {attempt + 1}/{retries}): {e}")
                time.sleep(2)
        logging.warning("All retry attempts failed!")
        return None
    
    def reset_and_reload_zone_information(self):
        self.reset()
        if self.process_zones(self.network.get(), self.get_zone()):
            if self.process_zone_information(self.network.get(), self.get_zone()):
                return True
            else:
                logging.warning("Download zone information failed")
                return False
        else:
            logging.warning("Download zones failed")
            return False
    
    def process_network(self, network_setup=None, network_current_ip=None):
        ipv4_address, ipv6_address = network_current_ip
        if network_setup and ipv4_address is not None and ipv6_address is not None:
            self.network.ipv4_address = ipv4_address
            self.network.ipv6_address = ipv6_address
            return True
        else:     
            return False 
        
    def process_zones(self, network=None, zone=None):
        network_data = network
        api_zone = network_data.api_zone

        if zone is None:
            logging.info("Requesting zones...")
            response = self.request_zones(network)
            if response and hasattr(response, 'status_code'):
                if response.status_code == 200: 
                    if self.save_zones(api_zone, response):
                        return True
                    else:
                        logging.warning(f"Failed to save zones:{response}")
                        return False
                else:
                    logging.warning(f"Failed to retrieve zones: {response} with: {response.text}")
                    return False
            else:
                logging.warning(f"Failed to retrieve zones: {response} with: {response.text}")
                return False
        else:
            return True

    def process_zone_information(self, network=None, zone=None):
        if self.get_zone_information() is None:
            logging.info("Requesting zone information...")
            if zone is not None:
                response = self.request_zone_information(network, zone.get("id"))
                if response and hasattr(response, 'status_code'):
                    if response.status_code == 200:
                        if self.save_zone_informations(response):
                            return True
                        else:
                            logging.warning(f"Failed to save zone information: {response}")
                            return False
                    else:
                        logging.warning(f"Failed to retrieve zone information: {response}")
                        return False
                else:
                    logging.warning(f"Failed to retrieve zone information: {response}")
                    return False
            else:
                logging.warning("No target zone found. Cannot retrieve zone information")
                return False
        else:
            return True
        
    def process_zone_information_update(self, network=None, zone=None, zone_information=None):        
        network_data = network
        ipv4_address = network_data.ipv4_address
        ipv6_address = network_data.ipv6_address
        a_records, aaaa_records = zone_information     
        reset_and_reload_zone = False

        if zone is None or zone_information is None or (ipv4_address is None and ipv6_address is None):
            return False

        def process_records(record_type, records, ip_address):
            has_www = False
            has_root = False

            if records and len(records) > 0:
                for record in records:
                    if record.get("type") == record_type:
                        if record.get("name") == f"www.{zone.get('name')}":
                            has_www = True
                        elif record.get("name") == zone.get("name"):
                            has_root = True

            if has_www and has_root and ip_address is not None:
                return "EXISTS"
            
            if (has_www is False or has_root is False) and ip_address is not None:
                if self.create_new_record(network, zone, type=record_type, ip_address=ip_address, disabled=False):
                    logging.info(f"Created missing {record_type} records for www and root")
                    return "NEW_RECORD"
                else:
                    logging.warning(f"Failed to create missing {record_type} records")
                    return False
                
            if len(records) > 0 and ip_address is None:
                all_deleted = True
                for record in records:
                    if self.delete_record(network, zone, record):
                        continue
                    else:
                        logging.warning(f"Failed to delete record {record_type}")
                        all_deleted = False
                
                if all_deleted:
                    logging.info(f"{record_type} records not needed because no IP fetched. Records deleted successfully")
                    return "DELETE_RECORD"
                else:
                    return False
                    
            if len(records) == 0 and ip_address is None:
                return "EMPTY_RECORD"
            
            logging.warning(f"Failed to process {record_type} records: {records} with {ip_address}")
            return False

        for record_type, records, ip_address in [("A", a_records, ipv4_address), ("AAAA", aaaa_records, ipv6_address)]:
            result = process_records(record_type, records, ip_address)
            if result in ["NEW_RECORD", "DELETE_RECORD"]:
                reset_and_reload_zone = True
            elif result == "EXISTS":
                pass
            elif result == "EMPTY_RECORD":
                pass
            else:
                logging.warning(f"Failed to process {record_type} records")
                return False

        if reset_and_reload_zone:
            return self.reset_and_reload_zone_information()
        else:
            return True
            
    def process_dynamic_dns_activation(self, network=None, zone_information=None):
        if self.get_dynamic_dns() is None and zone_information is not None:
            a_records, aaaa_records = zone_information
            if a_records or aaaa_records:
                record_name = a_records[0].get("name") if a_records else aaaa_records[0].get("name") if aaaa_records else None
                record_root_name = a_records[0].get("rootName") if a_records else aaaa_records[0].get("rootName") if aaaa_records else None
                response = self.request_activate_dynamic_dns(network, {
                    "domains": [record_name, record_root_name],
                    "description": record_root_name
                })

                if response and hasattr(response, 'status_code') and response.status_code == 200:
                    if self.save_dynamic_dns(response):
                        logging.info("DynDNS activated")
                        return True
                    else:
                        logging.warning("Failed to save DynDNS information")
                        return False
                elif response and hasattr(response, 'status_code'):
                    logging.warning(f"Failed to activate DynDNS: {response}")
                    return False
            else:
                logging.warning("No A or AAAA records found. Cannot activate DynDNS")
                return False
        elif self.get_dynamic_dns() is not None and zone_information is None:
            logging.warning("DynDNS is already activated. But zone information is empty")
            return False
        elif self.get_dynamic_dns() is not None and zone_information is not None:
            return True
        else:
            logging.warning("No DynDNS information found")
            return None
    
    def process_update_ip_address(self, network=None, zone=None, zone_information=None):
        network_data = network
        ipv4_address = network_data.ipv4_address
        ipv6_address = network_data.ipv6_address
        last_ipv4_address = network_data.last_ipv4_address
        last_ipv6_address = network_data.last_ipv6_address

        zone_information_ipv4 = zone_information[0]
        zone_information_ipv6 = zone_information[1]

        def process_ip_update(record_type, ip_address, last_ip_address, zone_information_records):
            for record in zone_information_records:
                if record.get("type") == record_type:
                    ip_in_record = record.get("content")
                    if ip_in_record != ip_address:
                        if self.update_record(network, zone.get("id"), record, ip_address):
                            logging.info(f"{record_type} address in record {record.get('name')} updated to: {ip_address}")
                            self.network.save_ip_address()
                        else:
                            return False
                    else:
                        logging.info(f"{record_type} address in record {record.get('name')} already up to date: {ip_in_record}. Skipping update")
                        self.network.save_ip_address()
            return True

        if not process_ip_update("A", ipv4_address, last_ipv4_address, zone_information_ipv4):
            return False

        if not process_ip_update("AAAA", ipv6_address, last_ipv6_address, zone_information_ipv6):
            return False

        return True
        
    def main(self):
        if self.process_network(self.network.setup(self.api_name, self.api_bulkId, self.api_key, self.api_zone, self.api_update_time), self.network.load_current_ip_address()) is not True:
            self.reset()   
            ipv4_address, ipv6_address = self.network.ipv4_address, self.network.ipv6_address
            logging.warning(f"Network check ipv4: {ipv4_address}, ipv6: {ipv6_address}")
            if ipv4_address:
                logging.info(f"Continuing with ipv4 address: {ipv4_address}")
            if ipv6_address:
                logging.info(f"Continuing with ipv6 address: {ipv6_address}")
            if ipv4_address is None and ipv6_address is None:
                logging.warning("No IP address found!\n")
        
        if self.process_zones(self.network.get(), self.get_zone()) is not True:
            self.reset()
            logging.warning("Download zones failed\n")

        if self.process_zone_information(self.network.get(), self.get_zone()) is not True:
            self.reset()
            logging.warning("Download zone information failed\n")

        if self.process_zone_information_update(self.network.get(), self.get_zone(), self.get_zone_information()) is not True:
            self.reset()
            logging.warning("Update zone information failed\n")

        if self.process_dynamic_dns_activation(self.network.get(), self.get_zone_information()) is not True:
            self.reset()
            logging.warning(f"DynDNS activation failed. Retrying in {self.api_update_time} minutes...\n")

        if self.get_dynamic_dns() is not None:
            if self.process_update_ip_address(self.network.get(), self.get_zone(), self.get_zone_information()):  
                self.reset()
                logging.info(f"Next check scheduled in {self.api_update_time} minutes\n")
            else:
                self.reset()
                logging.warning(f"IP address update failed. Retrying in {self.api_update_time} minutes...\n")

    def run_threaded(self):
        try:
            self.main()
        except Exception as e:
            logging.error(f"Error in main: {e}")
        finally:
            threading.Timer(self.api_update_time * 60, self.run_threaded).start()

if __name__ == "__main__":
    dyndns = IONOSDynDNS()
    dyndns.run_threaded()
