
# Viessmann Heat Pump MQTT Bridge

A Python script that creates a bridge between a Viessmann heat pump system and MQTT, allowing for monitoring and control of the heat pump through MQTT messages. The script reads various parameters from the heat pump and publishes them to MQTT topics, while also allowing control commands to be sent through MQTT.

## Features

- Reads numerous heat pump parameters (temperatures, statuses, operating modes, etc.)
- Publishes all values to MQTT topics with proper descriptions
- Allows control of specific heat pump parameters via MQTT
- Handles both numeric and enumerated (text-based) control commands
- Includes parameter validation and error handling
- Configurable update intervals
- Detailed logging

## Prerequisites

- Python 3.x
- `vclient` command-line tool installed and configured
- MQTT broker (e.g., Mosquitto)
- Access to Viessmann heat pump control interface

### Required Python packages:

```bash
pip install paho-mqtt
```

## Configuration

Edit the following constants in the script to match your setup:

```python
MQTT_HOST = "10.0.1.8"
MQTT_PORT = 1883
MQTT_BASE_TOPIC = "vito"
```

## Usage

### Running the Script

```bash
python3 vito_mqtt.py
```

### Reading Values

The script automatically publishes all heat pump values to MQTT topics in the format:
```
vito/<command>
```

Example payload:
```json
{
    "command": "getTempWWsoll",
    "description": "Hot water setpoint temperature",
    "value": 45.0,
    "timestamp": "2025-02-02 10:30:15"
}
```

### Setting Values

To control the heat pump, publish a message to:
```
vito/set/<command>
```

Currently supported set commands:

1. Hot Water Temperature
"vito/set/setTempWWsoll" -m '{"value": 46}'

2. Room Temperature
"vito/set/setRaum2" -m '{"value": 21}'

## Logging

The script includes comprehensive logging with the following format:
```
%(asctime)s - %(levelname)s - %(message)s
```

## Error Handling

The script includes error handling for:
- MQTT connection issues
- Invalid command values
- Command execution failures
- Parameter validation
- Timeout handling

## Contributing

Feel free to submit issues and pull requests.

- Based on the vclient interface for Viessmann heat pumps
- Uses the paho-mqtt library for MQTT communication

## To start

You can start if from shell:

```bash
vcontrold -x vcontrold.xml -d /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0

python3 vito_mqtt.py &
```

or use service files:

/etc/systemd/system/vcontrold.service

/etc/systemd/system/vito_mqtt.service


and then execute

```bash
sudo systemctl daemon-reload

sudo systemctl enable vcontrold.service
sudo systemctl enable vito_mqtt.service

sudo systemctl start vcontrold.service
sudo systemctl start vito_mqtt.service
```



