# Overview

This script is one of the components of my home-bew router-fail-over mechanism. The other components are
detailed further down in this readme. I created this mainly because I needed the backup router to have several
PoE+ ports for redundancy and this would be expendive to achieve in a pfsense box, so pfSync was not viable. 
(And because this seemed like a interesting project)

RS232 is utilized as an out-of-band communication medium for record and state communication 
between pfSense and RouterOS. When RouterOS detects pfSense is down, it automatically takes over
the routing role of pfSense. Once pfSense is back online, it will signal RouterOS to return 
to standby mode. 

As a whole, this script is application specific to my environment and use case. However, I attempted to take 
modularity into account. For example, `Mikrotik.py` is essentially a mostly standalone Mikrotik serial API / connector, 
akin to (and somewhat inspired by) https://github.com/d4vidcn/routeros_ssh_connector, just with a smaller
implementation scope.

---
# Quickstart
This section and the rest of this documentation assumes mikrotikSync is running on pfSense 2.6.0 unless otherwise stated.

1. Copy and/or rename `secrets_example.py` to `secrets.py`
    ```shell
    cp secrets_example.py secrets.py
    ```
2. Add RouterOS login credentials to `secrets.py`


3. (Recommended) Create a virtualenv for mikrotikSync.

    ```shell
    python3.8 -m venv ./venv
    chmod +x venv/bin/activate.csh
    source venv/bin/activate.csh
   ```

4. Install python modules
    ```shell 
    pip3 install -r requirements.txt
    ```

5. Run the script
    ```shell
    python3.8 main.py
    ```
    ```commandline
    Usage: main.py ACTION
    
    ACTION
    --sync
    Synchronize pfSense records to the backup RouterOS device
    --link_up
    Indicates to script that the network link is back up and sets the RouterOS device into 'switch mode'
    ```

6. Configure `/etc/devd.conf` 
   * See 'Configure devd.conf' 


7. Configure cronjob 
   * See 'Configure Cron'


8. (Optional) See `config.py` and `config_defaults.py` for additional options


---
### General Environment / Version Information
* Tested on Python 3.7, 3.8, and 3.11 on Windows 10
  * Relevant pfSense config files were copied over for the script to access during testing. The script is not intended to be run on Windows in 'production' though.
* pfSense 2.6.0-RELEASE
  * Python 3.8
* RouterOS 7.5
  * RouterOS Hardware is a RB5009UPr+S+IN
* FTDI FT232B/R UART for OOB serial link
---

## pfSense Configuration Details
pfSense has two jobs:
1. Periodically sync configuration changes to RouterOS (via `--sync` flag)
2. Notify RouterOS when it is back online (via `--link_up` flag)

### Preferences
Install Nano
```shell
pkg install nano
```
Update csh shell (default) to use Nano in crontab -e.
```shell
echo setenv EDITOR nano >> /etc/csh.cshrc
```
### Configure Cron
  * Add a cron job for `mikrotikSync --sync` to keep records up to date in RouterOS
    ```shell
    crontab -e
    ```
    ```
    @hourly /root/mikrotikSync/venv/bin/python3.8 /root/mikrotikSync/main.py --sync
    ```
    * This could also be done by monitoring the relevant files for changes, but this works for my scenario and is easier so... ¯\\\_(ツ)_/¯ 
    

### Configure devd.conf
* Edit `/etc/devd.conf` to run `mikrotikSync --link_up` when a network interface changes to LINK_UP
    ```
    notify 0 {
            match "system"          "IFNET";
            match "type"            "LINK_UP";
            media-type              "ethernet";
            action "service dhclient quietstart $subsystem";action "/root/mikrotikSync/env/bin/python3.8 /root/mikrotikSync/main.py --link_up";
    };
    ```
* Restart devd service
    ```shell
    service devd restart
    ```
---
## RouterOS Configuration Details

* RouterOS is managed by having two sets of configurations or 'modes' that it switches between. The normal, 
standby mode, is referred to as 'switch' mode, while the opposite mode is the 'router' mode.
* There are several scripts and conventions used to accomplish this.


### RouterOS Conventions
Desired state/configuration information is primarily stored in the comment strings of records. These comments 
indicate whether a record is 'managed' by `mikrotikSync` and whether it should be enabled/disabled in router/switch modes.

* All mikrotikSync records include `'Added by pfsense.'` in the comment string of records it has added.
   * Trivia: `Added by pfsense` is not parsed by any RouterOS script
* `mode:router` and `mode:switch` is used to indicate records to be enabled in `router mode` and `switch mode` respectively.
  * Records that do not match the desired mode are explicitly disabled when `setMode` is run. 
  * For example: All `mode:router` records are disabled by `setMode` when the desired mode is `switch mode`
* `global $mode` is used to store the desired mode. This must be set to either `router` or `switch` before running `setMode`
* Port 8 is **always** the 'WAN' port

---

## RouterOS Scripts
This section details the scripts that are run on RouterOS to facilitate mikrotikSync.

### /system/script/setMode
`/system/script/setMode` does the heavy lifting of configuring RouterOS. It parses the comments on
relevant records and enables/disables them according to the value of `global $mode`.

**Notes:**
* Changes the VLAN trunking of Ether7 and Ether8. 
  * In `switch mode` VLAN68 is tagged on Ether7 and Ether8, as VLAN68 is intended to be trunked through to another
  switch, eventually 'terminating' at pfSense as the WAN. In `router mode` RouterOS takes over as pfSense though, so VLAN68 
  'terminates' at RouterOS.
* WAN (VLAN68) interface list disabled in `switch mode` so WAN is not switched to LAN.
* pfSense MAC address is spoofed by RouterOS to make the transition slightly more seamless for clients.

```code
# valid options are router and switch
# get desired mode variable. valid options are 'router' and 'switch'
:global mode;
:log info [put "Setting configuration to $mode mode!"];

:local disableRouterStuff "null";
:local disableSwitchStuff "null";
# Rename disableRouterStuff to 'routerMode' and, likewise, 'switchMode'? Or maybe just be verbose and say 'disabledInSwitchMode' and 'disabledInRouterMode'?
# Light up SFP LED in router mode
:if ($mode = "router") do={
  /system/leds/set disabled=no [find leds=sfp-sfpplus1-led]
  :set disableRouterStuff "no"
  :set disableSwitchStuff "yes"
} else={
  :if ($mode = "switch") do={
  /system/leds/set disabled=yes [find leds=sfp-sfpplus1-led]
  :set disableRouterStuff "yes"
  :set disableSwitchStuff "no"
  } else={
    :error "Invalid mode selected. Exiting."
  }
}
:log info [put "Configured LED"];

# TODO: Sync pfsense upstream dns setting?
# Set whether we respond to DNS
/ip/dns/set allow-remote-requests=$disableSwitchStuff 
:log info [put "Configured DNS server"];

# Enable or disable static DNS entries
/ip/dns/static/set disabled=$disableRouterStuff [find comment~"mode:router"]
/ip/dns/static/set disabled=$disableSwitchStuff [find comment~"mode:switch"]
:log info [put "Configured Static DNS Entries"];

# Set DHCP server
/ip/dhcp-server/ set disabled=$disableRouterStuff [find comment~"mode:router"]
:log info [put "Configured DHCP Server"];

# Set local IP address
/ip/address set disabled=$disableRouterStuff [find comment~"mode:router"]
/ip/address set disabled=$disableSwitchStuff [find comment~"mode:switch"]
:log info [put "Configured Local IP"];

# Configure interface lists
/interface/list/member set disabled=$disableSwitchStuff [find comment~"mode:switch"]
/interface/list/member set disabled=$disableRouterStuff [find comment~"mode:router"]
:log info [put "Configured Interface Lists"];


# Set firewall rules
/ip/firewall/filter set disabled=$disableRouterStuff [find comment~"mode:router"]
/ip/firewall/nat set disabled=$disableRouterStuff [find comment~"mode:router"]
/ip/firewall/mangle set disabled=$disableRouterStuff [find comment~"mode:router"]
/ip/firewall/raw set disabled=$disableRouterStuff [find comment~"mode:router"]
:log info [put "Configured Firewall"];


# Configure MAC spoofing
:if ($mode = "router") do={
  /interface/ethernet/set ether8 mac-address=A4:BB:6D:23:E1:85
} else={
  :if ($mode = "switch") do={
    /interface/ethernet/set ether8 mac-address=18:FD:74:78:5D:DB
  }
}
:log info [put "Configured MAC Spoofing"];


# Configure VLAN68 tagging. 
:if ($mode = "router") do={
  # Ether7 should be untagged when in router mode so VLAN68 'terminates' here. 
  /interface/bridge/vlan/set untagged="" [find vlan-ids=68]
  /interface/bridge/vlan/set tagged=ether8 [find vlan-ids=68]
} else={ 
  :if ($mode = "switch") do={
    # Ether7 should be tagged vlan68 when in switch mode so vlan is trunked to next switch
    /interface/bridge/vlan/set untagged="" [find vlan-ids=68]
    /interface/bridge/vlan/set tagged=ether8,ether7 [find vlan-ids=68]
  }
}
:log info [put "Configured VLAN68"];


# Disable bridge ports that should not part of bridge (Such as WAN). 
# /interface/bridge/port is only physical ports, not VLAN.
/interface/bridge/port/set disabled=$disableRouterStuff [find comment~"mode:router"]
/interface/bridge/port/set disabled=$disableSwitchStuff [find comment~"mode:switch"]
:log info [put "Configured Bridge ports"];


# Set DHCP Client
/ip/dhcp-client/ set disabled=$disableRouterStuff [find comment~"mode:router"]
/ip/dhcp-client/ set disabled=$disableSwitchStuff [find comment~"mode:switch"]
:log info [put "Configured DHCP Client"];

:log info [put "Done configuring!"]
```
---
### `/system/script/pfDown`
This script configures the device for `router mode`. It is called by `/tools/netwatch` when pfsense (10.0.0.1) is down. I typically use a 10s timeout, 30s interval.

```code
:global mode
:set $mode "router"
:log info [put "Set global to $mode mode!"]/system/script/run setMode
```
**Note**: `netwatch` does not require the full `/system/script` path. Instead, just use the name of the script. 

---
### `/system/script/toSwitch`
This script configures the device for Switch mode and is called on boot by `/system/schedule`

```code
:global mode
:set $mode "switch"
:log info [put "Set global to $mode mode!"]
/system/script/run setMode
```

**Note**: `schedule` does not require the full `/system/script` path. Instead, just use the name of the script. 

---
## Limitations
* Only reserved/static DHCP and DNS records are synced to RouterOS at this time
* Records are read from pfSense and written to RouterOS. This script cannot sync changes from RouterOS to pfSense.
* Polling / Cron architecture
* ``--sync`` sends all records, even if no records have changed. 

---
## Possible Improvements
* Keep the WAN address from pfsense cached in RouterOS Address List for faster recovery.
* Remove cron polling and instead have the script only sync when there are changes made to `dhcpd.conf`, 
`dhcpd.leases`, or `host_entries.conf`
* Add system logging and integrate email alerts for critical errors
* Perform a differential sync instead of a 'full sync' for `--sync`. It doesn't matter too much for the number of 
records I have, but a differential sync could be much faster than the current (very inefficient) implementation. 
* Synchronize dynamic leases and such as well
* Add more options to the config file
* Use a 'real' config file format
* Expand `Mikrorik.py` into a more complete API

