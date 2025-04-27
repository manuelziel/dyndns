#!/bin/bash
#
# IONOS-DynDNS Setup Script
# This script sets up the IONOS-DynDNS service on a Linux system.
# It creates a systemd service, configures it, and installs the necessary files.
# It also provides options to install, update, and uninstall the service.
# 
# Author: Manuel Ziel
# Date: 27-04-2025
# Version: 1.0.2
# License: MIT
#
# This program is free software: you can redistribute it and/or modify

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if the script is run as root or with sudo
if [[ $EUID -ne 0 ]]; then
    printf "${RED}Run as root!${NC}\n"
    exit 1
fi

# Get the current directory and the current user
CURRENT_DIR=$(dirname "$(readlink -f "$0")")
CURRENT_USER=$(whoami)

# Template- and Service-Path
IONOS_DYNDNS_SERVICE_NAME="ionos-dyndns.service"
IONOS_DYNDNS_SERVICE_TEMPLATE_PATH="/etc/systemd/system/$IONOS_DYNDNS_SERVICE_NAME"

# Template for the systemd service
# See the README.md for more information on configuration options.
IONOS_DYNDNS_SERVICE_TEMPLATE="[Unit]
Description=IONOS DynDNS Service
After=network.target

[Service]
Environment=IONOS_API_NAME=NAME
Environment=IONOS_API_BULKID=API_BULKID
Environment=IONOS_API_KEY=API_KEY
Environment=IONOS_API_ZONE=ZONE
Environment=IONOS_API_UPDATE_TIME=UPDATE_TIME
ExecStart=/usr/bin/python3 /usr/local/bin/ionos-dyndns.py
StandardOutput=journal
StandardError=journal
Restart=always
User=${CURRENT_USER}

[Install]
WantedBy=multi-user.target"

NAME="NULL"
BULKID="NULL"
API_KEY="NULL"
ZONE="NULL"
UPDATE_TIME="5"
IONOS_DynDNS_CONFIG=false

function ask_for_confirmation() {
    printf "\n"
    printf "More information about IONOS-DynDNS can be found in the README.md\n"
    printf "Exit with Ctrl+C\n"
    printf "\n"
    while true; do
        read -p "Setup the IONOS-DynDNS with user: $CURRENT_USER? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            return 0
        elif [[ $REPLY =~ ^[Nn]$ ]]; then
            printf "Setup aborted\n"
            return 1
        else
            printf "Invalid input. Please enter 'y' or 'n'.\n"
        fi
    done
}

function ask_install_uninstall() {
    local templete_path=$1
    local service_name=$2
    while true; do
        read -p "Install/Update and configure IONOS-DynDNS? (y/n): " -n 1 -r
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            printf "\n"
            printf "${GREEN}Installing/Updating IONOS-DynDNS...${NC}\n"
            if ! stop_service $service_name; then
                return 1
            fi
            if ! check_python3; then 
                return 1
            fi
            if ! service_template $templete_path; then
                return 1
            fi
            if ! copy_files; then
                return 1
            fi 

            if start_service $service_name; then 
                printf "${GREEN}IONOS-DynDNS installed successfully${NC}\n"
                return 0
            else 
                printf "${RED}Error: Starting IONOS-DynDNS${NC}\n"
                return 1
            fi

        elif [[ $REPLY =~ ^[Nn]$ ]]; then
            printf "\n"
            while true; do
                read -p "Uninstall IONOS-DynDNS? (y/n): " -n 1 -r
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    printf "\n"
                    if uninstall $service_name $templete_path; then
                        return 0
                    else
                        return 1
                    fi
                elif [[ $REPLY =~ ^[Nn]$ ]]; then
                    printf "\n"
                    printf "Exiting setup script!\n"
                    return 1
                else
                    printf "\n"
                    printf "${RED}Invalid input. Please enter 'y' or 'n'.${NC}\n"
                fi
            done
        else
            printf "${RED}Invalid input. Please enter 'y' or 'n'.${NC}\n"
        fi
    done
}

function stop_service() {
    local service_name=$1
    if IONOS_DYNDNS_SERVICE_NAME=$(systemctl list-units --type=service | grep $service_name); then
        printf "Stopping the IONOS-DynDNS Service...\n"
        if systemctl is-active --quiet $service_name; then
            sudo systemctl stop $service_name
            if ! systemctl is-active --quiet $service_name; then
                printf "${GREEN}IONOS-DynDNS stopped successfully${NC}\n"
                return 0
            else
                printf "${RED}Error: Stopping IONOS-DynDNS${NC}\n"
                return 1
            fi
        else
            printf "${GREEN}IONOS-DynDNS is already stopped${NC}\n" 
            return 0   
        fi
    else
        return 0
    fi
    return 1
}

function check_python3() {
    if ! dpkg-query -W -f='${Status}' python3 2>/dev/null | grep -q "ok installed"; then
        printf "python3 could not be found, installing python3..."
        sudo apt update
        if sudo apt install -y python3; then
            if ! command -v python3 &> /dev/null; then
                printf "${RED}Error: python3 installation${NC}\n"
                return 1
            else 
                printf "${GREEN}python3 installed successfully${NC}\n"
                return 0
            fi
        else
            printf "${RED}Error: Installing python3${NC}\n"
            return 1
        fi
    else
        printf "python3 ${GREEN}INSTALLED${NC}\n"
        return 0
    fi
    return 1
}

function service_template() {
    local templete_path=$1
    printf "Check service template...\n"
    if [ ! -f "$templete_path" ]; then
        printf "${YELLOW}Service template not found, creating it...${NC}\n"
        if echo "$IONOS_DYNDNS_SERVICE_TEMPLATE" | sudo tee "$templete_path" > /dev/null; then # Do not change this line. Multiline string!
            printf "${GREEN}Service template created successfully${NC}\n"
            if configure_service $templete_path; then
                return 0
            else
                return 1
            fi
        else 
            printf "${RED}Error: Creating service template${NC}\n"
            return 1
        fi
    else
        printf "${GREEN}Service template found${NC}\n"
        while true; do
            read -p "Update the service template? (y/n): " -n 1 -r
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                printf "\n"
                printf "${GREEN}Updating service template...${NC}\n"
                echo "$IONOS_DYNDNS_SERVICE_TEMPLATE" | sudo tee "$templete_path" > /dev/null # Do not change this line. Multiline string!
                if [ $? -ne 0 ]; then
                    printf "${RED}Error: Updating service template${NC}\n"
                    return 1
                else 
                    printf "${GREEN}Service template updated successfully${NC}\n"
                fi

                if configure_service $templete_path; then
                    return 0
                else
                    return 1
                fi
            elif [[ $REPLY =~ ^[Nn]$ ]]; then
                printf "\n"
                printf "${YELLOW}Service template not updated${NC}\n"
                return 0
            else
                printf "\n"
                printf "${RED}Invalid input. Please enter 'y' or 'n'.${NC}\n"
            fi
        done
    fi
}

function configure_service() {
    local templete_path=$1
    local name
    local bulkId
    local api_key
    local zone
    local update_time
    
    while true; do
        read -p "Configure IONOS-DynDNS? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            printf "\n"
            printf "Please enter the following parameter\n"
            
            printf "Enter the name (Zugriffsschlüsselname)\n"
            printf "Enter the bulkId (Öffentlicher Präfix)\n"
            printf "Enter the api-key (API-Zugriffsschlüssel)\n"
            printf "Enter the zone (eg. example.com)\n"
            printf "Enter the update time in minutes (default: 5)\n"

            read -p "name: " name
            read -p "bulkId: " bulkId
            read -p "api-key: " api_key
            read -p "zone: " zone
            read -p "Update time (default: 5): " update_time

            printf "\n"
            printf "You entered the following information:\n"
            printf "Name: ${name}\n"
            printf "BulkId: ${bulkId}\n"
            printf "API-Key: ${api_key}\n"
            printf "Zone: ${zone}\n"
            printf "Update time: ${update_time}\n"

            while true; do
                read -p "Is the input correct? (y/n): " -n 1 -r
                printf "\n\n"

                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    printf "${RED}Ensure that port 80 and 443 on this server are not blocked by a firewall!${NC}\n"
                    printf "\n"

                    while true; do
                        read -p "Do you want to continue? (y/n): " -n 1 -r
                        printf "\n"

                        if [[ $REPLY =~ ^[Yy]$ ]]; then
                            if configure_service_template $templete_path $name $bulkId $api_key $zone $update_time; then
                                return 0
                            else 
                                return 1
                            fi
                        elif [[ $REPLY =~ ^[Nn]$ ]]; then
                            break
                        else
                            printf "${RED}Invalid input. Enter 'y' or 'n'.${NC}\n"
                        fi
                    done
                elif [[ $REPLY =~ ^[Nn]$ ]]; then
                    printf "\n"
                    printf "${RED}Enter the parameters again${NC}\n"
                    break
                else
                    printf "\n"
                    printf "${RED}Invalid input. Enter 'y' or 'n'.${NC}\n"
                fi
            done
        elif [[ $REPLY =~ ^[Nn]$ ]]; then
            printf "\n"
            printf "${YELLOW}Configuration skipped${NC}\n"
            return 0
        else
            printf "\n"
            printf "${RED}Invalid input. Enter 'y' or 'n'.${NC}\n"
        fi
    done
}

function configure_service_template() {
    local templete_path=$1
    local name=$2
    local bulkId=$3
    local api_key=$4
    local zone=$5
    local update_time=$6

    printf "Configuring the IONOS-DynDNS...\n"
    
    if ! sudo sed -i "s|^Environment=IONOS_API_NAME=.*|Environment=IONOS_API_NAME=$name|g" "$templete_path"; then
        printf "${RED}Error: Setting IONOS_API_NAME${NC}\n"
        return 1
    fi
    
    if ! sudo sed -i "s|^Environment=IONOS_API_BULKID=.*|Environment=IONOS_API_BULKID=$bulkId|g" "$templete_path"; then
        printf "${RED}Error: Setting IONOS_API_BULKID${NC}\n"
        return 1
    fi
    
    if ! sudo sed -i "s|^Environment=IONOS_API_KEY=.*|Environment=IONOS_API_KEY=$api_key|g" "$templete_path"; then
        printf "${RED}Error: Setting IONOS_API_KEY${NC}\n"
        return 1
    fi

    if ! sudo sed -i "s|^Environment=IONOS_API_ZONE=.*|Environment=IONOS_API_ZONE=$zone|g" "$templete_path"; then
        printf "${RED}Error: Setting IONOS_API_ZONE${NC}\n"
        return 1
    fi

    if ! sudo sed -i "s|^Environment=IONOS_API_UPDATE_TIME=.*|Environment=IONOS_API_UPDATE_TIME=$update_time|g" "$templete_path"; then
        printf "${RED}Error: Setting IONOS_API_UPDATE_TIME${NC}\n"
        return 1
    fi

    return 0
}

function copy_files() {
    local file="ionos-dyndns.py"
    local file_path="/usr/local/bin/$file"

    printf "Copying IONOS-DynDNS files...\n"

    if ! sudo cp $file "$file_path"; then
        printf "${YELLOW}No local file found, downloading it from git...${NC}\n"
        if ! curl -sL https://github.com/manuelziel/dyndns/raw/main/ionos-dyndns.py -o "$file_path"; then
            printf "${RED}Error: Downloading files from git${NC}\n"
            return 1
        else
            printf "${GREEN}Files downloaded successfully${NC}\n"
        fi
    fi

    if ! sudo chmod +x "$file_path"; then
        printf "${RED}Error: Setting permissions for IONOS-DynDNS files${NC}\n"
        return 1
    fi
    
    return 0
}

function uninstall() {
    local service_name=$1
    local templete_path=$2

    local file="ionos-dyndns.py"
    local file_path="/usr/local/bin/$file"

    printf "${GREEN}Uninstalling IONOS-DynDNS...${NC}\n"
    
    if ! sudo systemctl stop "$service_name"; then
        printf "${RED}Error: Stopping IONOS-DynDNS service. Service already stopped?${NC}\n"
    fi

    if ! sudo systemctl disable "$service_name"; then
        printf "${RED}Error: Disabling IONOS-DynDNS service. Service already disabled?${NC}\n"
    fi
   
    if ! sudo rm -f "$file_path"; then
        printf "${RED}Error: Removing IONOS-DynDNS files. File $file_path already removed?${NC}\n"
    fi

    if ! sudo rm -f "$templete_path"; then
        printf "${RED}Error: Removing service template. Path $templete_path already removed?${NC}\n"
    fi
    return 0
}

function start_service() {
    local service_name=$1
    local service_status_enabled=$(systemctl is-enabled "$service_name" 2>/dev/null)
    local service_status_active=$(systemctl is-active "$service_name" 2>/dev/null)

    if ! sudo systemctl daemon-reload; then
        printf "${RED}Error: Reloading systemd${NC}\n"
        return 1
    fi

    if ! sudo systemctl enable ionos-dyndns.service; then
        printf "${RED}Error: Enabling $service_name${NC}\n"
        return 1
    fi

    if [ "$service_status_active" == "active" ]; then
        printf "${GREEN}Service $service_name is already active${NC}\n"
        return 0
    else
        printf "Starting the service $service_name...\n"
        if sudo systemctl start "$service_name"; then
            printf "${GREEN}Service $service_name started successfully${NC}\n"
            return 0
        else
            printf "${RED}Error: Starting $service_name${NC}\n"
            return 1
        fi
    fi
}

function main() {
    if ! ask_for_confirmation; then
        exit 1
    fi
    if ask_install_uninstall $IONOS_DYNDNS_SERVICE_TEMPLATE_PATH $IONOS_DYNDNS_SERVICE_NAME; then
        exit 1
    fi
}

main