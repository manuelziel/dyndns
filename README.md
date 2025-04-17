# IONOS DynDNS

**IONOS DynDNS** is a Python script designed to dynamically update DNS records (A and AAAA) for your domain hosted on IONOS. This script is particularly useful for users with dynamic IP addresses, allowing them to automatically synchronize their DNS records with their current public IP address.

---

## **How It Works**

The script:
- **Detects** your system's current public IPv4 and/or IPv6 address.
- **Connects** to the IONOS DNS API.
- **Finds** the appropriate DNS zone for your domain.
- **Updates** the A and/or AAAA records for the specified hostname (FQDN) with the current IP address.
- **Deletes** the wrong and unused A and/or AAAA records for the specified hostname (FQDN).
- **Activates** Dynamic DNS (DynDNS) for your domain if required.

---

## **Requirements**

- An **IONOS account** with access to the DNS API.
- **Python 3.6** or higher.
- An existing DNS zone for the domain you want to update.

---

## **Installation**

### **Automated Installation**

Run the following command to install IONOS DynDNS automatically:

```bash
bash -c "$(wget -qO- https://github.com/manuelziel/dyndns/raw/main/scripts/install.sh)"
```
### **Manual Installation**
Clone the repository:
```bash
git clone https://github.com/manuelziel/dyndns.git
cd dyndns
```
Run the script
```bash
sudo bash setup.sh
```
### **Run Manually**
Run the folling command to run it manually:
```bash
python3 ionos-dyndns.py
```

### **Required Inputs During Installation**
During the installation or update process, you will be prompted to provide the following information:
- **Name** (Zugriffsschlüsselname)      eg (name of the key)
- **BulkId** (Öffentlicher Präfix)      eg (2f8040a4506f40a20bb30be0100a000c)
- **API-Key** (API-Zugriffsschlüssel)   eg (kaVaReauMaPaSgaflaXnaqea4CGa2OFaaZaiQaTpaUYatzaM2aTaS2rrdr0PcAi4AEJRAx5Awasa0bUD0B-0aA)
- **Zone** (e.g., example.com)
- **Update Time** in minutes (default: 5)

---

## **Troubleshooting**

### **Common Issues**

1. **IPv6 Address Not Found:**
   - Ensure your system supports IPv6 and has a public IPv6 address.
   - Test IPv6 connectivity:
     ```bash
     ping6 google.com
     ```

2. **Missing Environment Variables:**
   - Ensure all required environment variables are set in /etc/systemd/system/ionos-dyndns.service:
     ```bash
     export IONOS_API_NAME="YOUR_API_NAME"
     export IONOS_API_BULKID="YOUR_BULKID"
     export IONOS_API_KEY="YOUR_API_KEY"
     export IONOS_API_ZONE="YOUR_ZONE"
     export IONOS_API_UPDATE_TIME=5
     ```

3. **Service Not Starting:**
   - Check the logs for errors:
     ```bash
     sudo journalctl -u ionos-dyndns.service
     ```
     or check service:

     ```bash
     sudo systemctl status ionos-dyndns.service
     ```

---

## **Contributing**

We welcome contributions! If you'd like to report an issue, suggest a feature, or contribute code, feel free to open an issue or submit a pull request on GitHub.

---

## **License**

This project is licensed under the **MIT License**. See the `LICENSE` file for details.

---

## **Contact**

- **Author:** Manuel Ziel
- **GitHub:** [manuelziel](https://github.com/manuelziel)
- **IONOS DNS API Documentation:** [IONOS Developer Docs](https://developer.hosting.ionos.de/docs/dns)
```

---
