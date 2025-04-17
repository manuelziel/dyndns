#!/bin/bash
#
# IONOS-DynDNS Setup Script
# This script sets up the IONOS-DynDNS service on a Linux system.
# It creates a systemd service, configures it, and installs the necessary files.
# It also provides options to install, update, and uninstall the service.
# 
# Author: Manuel Ziel
# Date: 17-04-2025
# Version: 1.0
# License: MIT
#
# This program is free software: you can redistribute it and/or modify


printf "Starting the setup script for IONOS-DynDNS...\n"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if the script is run as root or with sudo
if [[ $EUID -ne 0 ]]; then
    printf "${RED}Run as root${NC}\n"
    exit 1
fi

# Get the current directory and the current user
CURRENT_DIR=$(dirname "$(readlink -f "$0")")
CURRENT_USER=$(whoami)

# Template- and Service-Path
IONOS_DYNDNS_SERVICE_TEMPLATE_PATH="/etc/systemd/system/ionos-dyndns.service"

# Template for the systemd service
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
    read -p "setup the IONOS-DynDNS with user: $CURRENT_USER? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        printf "Setup aborted\n"
        exit 1
    fi
    return 0
}

function ask_install_uninstall() {
    read -p "install/update and configure IONOS-DynDNS? (y/n): " -n 1 -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        printf "${GREEN}Install/Updating IONOS-DynDNS...${NC}\n"
        stop_service
        check_python3
        service_template
        copy_files

        if start_service; then 
            exit 1
        else 
            exit 1
        fi

    elif [[ $REPLY =~ ^[Nn]$ ]]; then
        printf "\n"
        read -p "uninstall IONOS-DynDNS? (y/n): " -n 1 -r
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            if uninstall; then
                exit 0
            else
                exit 1
            fi
        elif [[ $REPLY =~ ^[Nn]$ ]]; then
                printf "\n"
                printf "Exiting setup script!\n"
        fi
    else
        printf "${RED}Invalid option.${NC}\n"
    fi
}

function stop_service() {
    if IONOS_DYNDNS_SERVICE_NAME=$(systemctl list-units --type=service | grep ionos-dyndns.service); then
        printf "Stopping the IONOS-DynDNS Service...\n"
        if systemctl is-active --quiet ionos-dyndns.service; then
            sudo systemctl stop ionos-dyndns.service
            if ! systemctl is-active --quiet ionos-dyndns.service; then
                printf "${GREEN}IONOS-DynDNS stopped successfully${NC}\n"
                return 0
            else
                printf "${RED}Error: Stopping IONOS-DynDNS${NC}\n"
                exit 1
            fi
        else
            printf "IONOS-DynDNS is already stopped\n"    
        fi
    else
        return 1
    fi
}

function check_python3() {
    if ! dpkg-query -W -f='${Status}' python3 2>/dev/null | grep -q "ok installed"; then
        printf "python3 could not be found, installing python3..."
        sudo apt update
        if sudo apt install -y python3; then
            if ! command -v python3 &> /dev/null; then
                printf "${RED}Error: python3 installation${NC}\n"
                exit 1
            else 
                printf "${GREEN}python3 installed successfully${NC}\n"
            fi
        else
            printf "${RED}Error: Installing python3${NC}\n"
            exit 1
        fi
    else
        printf "python3 ${GREEN}INSTALLED${NC}\n"
    fi
    return 0
}

function service_template() {
    printf "Check service template...\n"
    if [ ! -f "$IONOS_DYNDNS_SERVICE_TEMPLATE_PATH" ]; then
        printf "${YELLOW}Service template not found, creating it...${NC}\n"
        echo "$IONOS_DYNDNS_SERVICE_TEMPLATE" | sudo tee "$IONOS_DYNDNS_SERVICE_TEMPLATE_PATH" > /dev/null
        if [ $? -ne 0 ]; then
            printf "${RED}Error: Creating service template${NC}\n"
            return 1
        fi
        printf "${GREEN}Service template created successfully${NC}\n"
        if configure_service; then
            configure_service_template $NAME $BULKID $API_KEY $ZONE $UPDATE_TIME 
        fi
        return 0
    else
        printf "${GREEN}Service template found${NC}\n"
        read -p "Do you want to update the service template? (y/n): " -n 1 -r
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            printf "${GREEN}Updating service template...${NC}\n"
            echo "$IONOS_DYNDNS_SERVICE_TEMPLATE" | sudo tee "$IONOS_DYNDNS_SERVICE_TEMPLATE_PATH" > /dev/null
            if [ $? -ne 0 ]; then
                printf "${RED}Error: Updating service template${NC}\n"
                return 1
            fi

            if configure_service; then
                configure_service_template $NAME $BULKID $API_KEY $ZONE $UPDATE_TIME 
                return 0
            else
                printf "${RED}Service template not configured${NC}\n"
                return 1
            fi
        else
            printf "${YELLOW}Service template not updated${NC}\n"
            return 0
        fi
    fi
}

function configure_service() {
    local name
    local bulkId
    local api_key
    local zone
    local update_time

    read -p "Configure IONOS-DynDNS? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        printf "\nPlease enter the following parameter\n"
        while true; do
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

            printf "\nYou entered the following information:\n"
            printf "Name: ${name}\n"
            printf "BulkId: ${bulkId}\n"
            printf "API-Key: ${api_key}\n"
            printf "Zone: ${zone}\n"
            printf "Update time: ${update_time}\n"

            read -p "Is the input correct? (y/n): " -n 1 -r
            printf "\n\n"

            if [[ $REPLY =~ ^[Yy]$ ]]; then
                printf "${RED}Ensure that port 80 and 443 on this server are not blocked by a firewall!${NC}\n"
                printf "\n"

                read -p "Do you want to continue? (y/n): " -n 1 -r
                printf "\n"

                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    NAME=$name
                    BULKID=$bulkId
                    API_KEY=$api_key
                    ZONE=$zone
                    UPDATE_TIME=$update_time
                    return 0
                    break
                fi
            fi
        done
    else
        printf "${RED}Configuration skipped${NC}\n"
        return 1
    fi
}

function configure_service_template() {
    local name=$1
    local bulkId=$2
    local api_key=$3
    local zone=$4
    local update_time=$5

    printf "Configuring the IONOS-DynDNS...\n"
    
    sudo sed -i "s|^Environment=IONOS_API_NAME=.*|Environment=IONOS_API_NAME=$name|g" "$IONOS_DYNDNS_SERVICE_TEMPLATE_PATH"
    if [ $? -ne 0 ]; then
        printf "${RED}Error: Setting IONOS_API_NAME${NC}\n"
        return 1
    fi
    sudo sed -i "s|^Environment=IONOS_API_BULKID=.*|Environment=IONOS_API_BULKID=$bulkId|g" "$IONOS_DYNDNS_SERVICE_TEMPLATE_PATH"
    if [ $? -ne 0 ]; then
        printf "${RED}Error: Setting IONOS_API_BULKID${NC}\n"
        return 1
    fi
    sudo sed -i "s|^Environment=IONOS_API_KEY=.*|Environment=IONOS_API_KEY=$api_key|g" "$IONOS_DYNDNS_SERVICE_TEMPLATE_PATH"
    if [ $? -ne 0 ]; then
        printf "${RED}Error: Setting IONOS_API_KEY${NC}\n"
        return 1
    fi
    sudo sed -i "s|^Environment=IONOS_API_ZONE=.*|Environment=IONOS_API_ZONE=$zone|g" "$IONOS_DYNDNS_SERVICE_TEMPLATE_PATH"
    if [ $? -ne 0 ]; then
        printf "${RED}Error: Setting IONOS_API_ZONE${NC}\n"
        return 1
    fi
    sudo sed -i "s|^Environment=IONOS_API_UPDATE_TIME=.*|Environment=IONOS_API_UPDATE_TIME=$update_time|g" "$IONOS_DYNDNS_SERVICE_TEMPLATE_PATH"
    if [ $? -ne 0 ]; then
        printf "${RED}Error: Setting IONOS_API_UPDATE_TIME${NC}\n"
        return 1
    fi

    return 0
}

function copy_files() {
    printf "Copying IONOS-DynDNS files...\n"
    sudo cp ionos-dyndns.py /usr/local/bin/ionos-dyndns.py
    if [ $? -ne 0 ]; then
        printf "${RED}Error: Copying IONOS-DynDNS files${NC}\n"
        return 1
    fi

    sudo chmod +x /usr/local/bin/ionos-dyndns.py
    if [ $? -ne 0 ]; then
        printf "${RED}Error: Setting permissions for IONOS-DynDNS files${NC}\n"
        return 1
    fi
    
    return 0
}

function uninstall() {
    printf "\n"
    printf "${GREEN}Uninstalling IONOS-DynDNS...${NC}\n"
    
    sudo systemctl stop ionos-dyndns.service
    sudo systemctl disable ionos-dyndns.service
    sudo rm -f /usr/local/bin/ionos-dyndns.py
    sudo rm -f "$IONOS_DYNDNS_SERVICE_TEMPLATE_PATH"

    printf "${GREEN}IONOS-DynDNS uninstalled successfully${NC}\n"
    return 0
}

function start_service() {
    IONOS_DYNDNS_SERVICE_NAME="ionos-dyndns.service"
    IONOS_DYNDNS_SERVICE_STATUS=$(systemctl is-enabled "$IONOS_DYNDNS_SERVICE_NAME" 2>/dev/null)

    sudo systemctl daemon-reload
    if [ $? -ne 0 ]; then
        printf "${RED}Error: Reloading systemd${NC}\n"
        return 1
    fi

    sudo systemctl enable ionos-dyndns.service
    if [ $? -ne 0 ]; then
        printf "${RED}Error: Enabling $IONOS_DYNDNS_SERVICE_NAME${NC}\n"
        return 1
    fi

    if [ "$IONOS_DYNDNS_SERVICE_STATUS" == "enabled" ]; then
        printf "${GREEN}Service $IONOS_DYNDNS_SERVICE_NAME is already active${NC}\n"
        return 0
    else
        printf "Starting the service $IONOS_DYNDNS_SERVICE_NAME...\n"
        sudo systemctl start "$IONOS_DYNDNS_SERVICE_NAME"
        if systemctl is-active --quiet "$IONOS_DYNDNS_SERVICE_NAME"; then
            printf "${GREEN}Service $IONOS_DYNDNS_SERVICE_NAME started successfully${NC}\n"
            return 0
        else
            printf "${RED}Error: Starting $IONOS_DYNDNS_SERVICE_NAME${NC}\n"
            return 1
        fi
    fi
}

function main() {
    ask_for_confirmation
    ask_install_uninstall
}

main