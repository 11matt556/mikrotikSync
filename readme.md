# Overview

This script is one of the main components in my home-bew router-fail-over mechanism. pfSense CARP / HA 
was not viable for my environment since one of the requirements of the fail-over router is multiple PoE+ ports for
power redundancy.

RS232 is utilized as an out-of-band communication medium for record and state communication between pfSense and RouterOS.

As a whole, this script is application specific to my environment and use case. However, modularity and separation of 
concerns were taken into account. For example, `Mikrotik.py` is essentially a mini Mikrotik serial API / connector, 
akin to (and somewhat inspired by) https://github.com/d4vidcn/routeros_ssh_connector.
---
# Quickstart

1. Install required packages
```commandline
pip3 install -r requirements.txt
```

2. Copy and rename `secrets_example.py` to `secrets.py`
```commandline
cp secrets_example.py secrets.py
```

3. Update `routeros_username` and `routeros_password` with your RouterOS username and password.


4. Run script without arguments to see help text
```commandline
python main.py
Usage: main.py ACTION

ACTION
--sync
Synchronize pfSense records to the backup RouterOS device
--link_up
Indicates to script that the network link is back up and sets the RouterOS device into 'switch mode'
```

5. See `config.py` and `config_defaults.py` for additional options
---
### Supported Python Versions
* Supports Python 3.7 and higher.
  * Testing performed using Python 3.7, 3.8, and 3.11
---
## pfSense Configuration

### Personal Configuration Preferences
* `pkg install nano` 
  * Because I can't be bothered with vim
* `echo "EDITOR=/usr/bin/nano" >> /etc/profile`
  * So I don't have to use vim in crontab
### Recommended Configuration for pfSync Usage
* Run `pfSync` with the `--link_up` flag when a network interface changes to LINK_UP status
  * This is accomplished by adding the script to LINK_UP in `/etc/devd.conf`.
    ```shell
    notify 0 {
            match "system"          "IFNET";
            match "type"            "LINK_UP";
            media-type              "ethernet";
            action "service dhclient quietstart $subsystem";action "/usr/local/bin/python3.8 /path/to/script/main.py --link_up";
    };
    ```
* Run `pfSync` with the `--sync` flag periodically to keep records up to date in RouterOS
    ```shell
    crontab -e
    @hourly /usr/local/bin/python3.8 /path/to/script/main.py --sync
    ```
    
# RouterOS
* RouterOS is managed by having two sets of configurations or 'modes' that it switches between. The normal, 
standby mode, is referred to as 'switch' mode, while the opposite mode is the 'router' mode.
* There are several scripts and conventions used to accomplish this.
#### RouterOS Conventions
1. This script creates a comment with `'Added by pfsense.'` on every record added or 'managed' by this script.
   * Trivia: `Added by pfsense` is parsed by this script, but not by anything on RouterOS
2. Add `'mode:router'` to the comment of any record that should be enabled in 'router mode' and disabled in 'switch mode'.
3. Add `'mode:switch'` to the comment for likewise behavior, but for 'switch mode'
   *   `/system/script/setMode` does the heavy lifting for these 'modes'
4. `global $mode` is used to store the current mode and acts as the 'mode parameter' for `setMode`

---
## RouterOS Scripting
### `/system/script/setMode`
`/system/script/setMode` does the heavy lifting of configuring RouterOS. Its role is to parse the comments on
relevant records and enable or disable them depending on the comment values and the value of `global $mode`.
```shell
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

# TODO: Sync pfsense upstream dns setting?
# Set whether it responds to DNS
/ip/dns/set allow-remote-requests=$disableSwitchStuff 

# Enable or disable static DNS entries
/ip/dns/static/set disabled=$disableRouterStuff [find comment~"mode:router"]
/ip/dns/static/set disabled=$disableSwitchStuff [find comment~"mode:switch"]

# Set DHCP server
/ip/dhcp-server/ set disabled=$disableRouterStuff [find comment~"mode:router"]

# Set local IP address
/ip/address set disabled=$disableRouterStuff [find comment~"mode:router"]
/ip/address set disabled=$disableSwitchStuff [find comment~"mode:switch"]

# Configure interface lists
/interface/list/member set disabled=$disableSwitchStuff [find comment~"mode:switch"]
/interface/list/member set disabled=$disableRouterStuff [find comment~"mode:router"]

# Set firewall rules
/ip/firewall/filter set disabled=$disableRouterStuff [find comment~"mode:router"]
/ip/firewall/nat set disabled=$disableRouterStuff [find comment~"mode:router"]
/ip/firewall/mangle set disabled=$disableRouterStuff [find comment~"mode:router"]
/ip/firewall/raw set disabled=$disableRouterStuff [find comment~"mode:router"]

# Configure MAC spoofing
:if ($mode = "router") do={
  /interface/ethernet/set ether8 mac-address=A4:BB:6D:23:E1:85
} else={
  :if ($mode = "switch") do={
    /interface/ethernet/set ether8 mac-address=18:FD:74:78:5D:DB
  }
}

# Configure VLAN68 tagging. 
# Ether7 should be untagged when in router mode so that the switch connected on Ether7 can pick up the LAN from this router. 
:if ($mode = "router") do={
  /interface/bridge/vlan/set untagged="" [find vlan-ids=68]
  /interface/bridge/vlan/set tagged=ether8 [find vlan-ids=68]

} else={ 
  :if ($mode = "switch") do={
    # Ether7 should be tagged vlan68 when in switch mode so vlan passes through to next switch
    /interface/bridge/vlan/set untagged="" [find vlan-ids=68]
    /interface/bridge/vlan/set tagged=ether8,ether7 [find vlan-ids=68]
  }
}

# Disable bridge ports that should not part of bridge (Such as WAN)
/interface/bridge/port/set disabled=$disableRouterStuff [find comment~"mode:router"]
/interface/bridge/port/set disabled=$disableSwitchStuff [find comment~"mode:switch"]

# Set DHCP Client
/ip/dhcp-client/ set disabled=$disableRouterStuff [find comment~"mode:router"]
/ip/dhcp-client/ set disabled=$disableSwitchStuff [find comment~"mode:switch"]

:log info [put "Done reconfiguring!"]
```
---
### `/system/script/pfDown`
This script is called by `/tools/netwatch` when pfsense (10.0.0.1) is down. I typically go with a 10s timeout, 30s interval.

**Note**: netwatch does not require the full `/system/script` path. Instead, just use the name of the script. 

```shell
:global mode
:set $mode "router"
:log info [put "Set global to $mode mode!"]/system/script/run setMode
```
---

## Limitations
* Only reserved/static DHCP and DNS records are synced to RouterOS at this time
* Records are read from pfSense and written to RouterOS. This script does not change any configurations on pfSense.


## Possible Improvements
* Remove cron polling and instead have the script only sync when there are changes made to `dhcpd.conf`, 
`dhcpd.leases`, or `host_entries.conf`
* Add system logging and integrate email alerts for critical errors
* Perform a differential sync instead of a 'full sync' for `--sync`. It doesn't matter too much for the number of 
records I have, but a differential sync could be much faster than the current (very inefficient) implementation. 
* Synchronize dynamic leases and such as well
* Add more options to the config file
* Use a 'real' config file format