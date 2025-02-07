#!/usr/bin/env python3
import subprocess
import json
import paho.mqtt.client as mqtt
import time
import logging
import re

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# MQTT Configuration
MQTT_HOST = "10.0.1.8"
MQTT_PORT = 1883
MQTT_BASE_TOPIC = "vito"
MQTT_SET_TOPIC = f"{MQTT_BASE_TOPIC}/set/#"

# Dictionary of commands and their English translations
PLAUSIBLE_COMMANDS = {
    "getStatusQuellePri1": "Primary source status",
    "getStatusVentilWW": "DHW valve status",
    "getTempA": "Outside temperature",
    "getTempWWObenIst": "Current DHW top temperature",
    "getTempWWsoll": "Hot water setpoint temperature",
    "getWWBereitung": "DHW preparation status",
    "getTempVL": "Supply temperature",
    "getTempRL": "Return temperature",
    "getTempVListHK1": "Supply temperature HK1",
    "getTempRListHK1": "Return temperature HK1",
    "getTempVLsollM2": "Supply setpoint temperature for M2",
    "getTempSTSSOL": "Tank temperature (solar low-pass)",
    "getMischerM3": "Mixing valve position M3",
    "getBetriebArtHK1": "Operating mode HK1",
    "getBetriebArtHK2": "Operating mode HK2",
    "getTimerWWMo": "Monday DHW schedule",
    "getStatusVentilatorstufe1": "ABC",
    "getStatusVentilatorstufe2": "ABC",
    "getRaumtemperaturIst": "ABC",
    "getRaum2": "ABC"
}

SUSPICIOUS_COMMANDS = {
    "getWWUWPNachlauf": "DHW pump post-run time",
    "getSpeichervorrang": "Priority storage for heating circuit A1/M1",
    "getSpeichervorrangM2": "Priority storage for heating circuit M2",
    "getSpeichervorrangM3": "Priority storage for heating circuit M3",
    "getDevType": "Device type/System identification",
    "getCtrlId": "Controller identification",
    "getPanelSWIndex": "Control panel software index",
    "getKsCardType": "KS card type",
    "getUmschaltventil": "DHW/Heating diverter valve status"
}

ADDITIONAL_COMMANDS = {
    "getBetriebsmodus": "Operating mode (0=off, 1=WW, 2=WW+heating/cooling, 66=party)",
    "getManuellerModus": "Manual mode (0=off, 1=Heating, 2=One-time WW on Temp2)",
    "getKompressorBelastung1": "Compressor hours, load class 0–22K",
    "getKompressorBelastung2": "Compressor hours, load class 22–32K",
    "getKompressorBelastung3": "Compressor hours, load class 32–41K",
    "getKompressorBelastung4": "Compressor hours, load class 42–50K",
    "getKompressorBelastung5": "Compressor hours, load class 51–99K",
    "getEnergieWaermeWW12M": "Thermal energy for DHW (12 months)",
    "getEnergieWaermeHeizen12M": "Thermal energy for heating (12 months)",
    "getEnergieElektroWW1W": "Electrical energy for DHW (1 week)",
    "getEnergieWaermeWW1W": "Thermal energy for DHW (1 week)",
    "getEnergieElektroHeizen1W": "Electrical energy for heating (1 week)",
    "getEnergieWaermeHeizen1W": "Thermal energy for heating (1 week)",
    "getHysterese": "Heating circuit hysteresis (0.5–3)",
    "getKuehlkennlinieNiveau": "Cooling curve level",
    "getKuehlkennlinieSteigung": "Cooling curve slope",
    "getMinVLTempKuehlung": "Minimum supply temperature for cooling",
    "getTempDiffKuehlung": "Temperature differential for cooling",
    "getFreigabeKuehlung": "Enable cooling (0/1)",
    "getTempDiffHeizung": "Temperature differential for heating",
    "getStatusVentilatorstufe1": "Fan stage 1 status",
    "getStatusVentilatorstufe2": "Fan stage 2 status",
    "getStatusKaeltekreisumkehr": "Refrigerant circuit reversal status",
    "getAussentemperaturRegelung": "Outdoor temperature (for controller)",
    "getAussentemperatur2": "Outdoor temperature sensor 2",
    "getAussentemperatur3": "Outdoor temperature sensor 3",
    "getAussentemperatur4": "Outdoor temperature sensor 4",
    "getAussentemperatur5": "Outdoor temperature sensor 5",
    "getRaumtemperaturIST": "Room temperature (Vitotrol HK1)",
    "getRaumtemperaturParty": "Party-mode room temperature (Heating Circuit A1/HK1)",
    "getJAZgesamt": "Seasonal performance factor (overall)"
}


# Define settable parameters with their valid ranges and accepted values
SETTABLE_PARAMETERS = {
    "setTempWWsoll": {
        "type": "numeric",
        "min": 0,
        "max": 60,
        "description": "Set hot water setpoint temperature"
    },
    "setRaum2": {
        "type": "numeric",
        "min": 0,
        "max": 30,
        "description": "Set wanted room temperature"
    },
    "setBetriebsmodus": {
        "type": "enum",
        "values": ["ABSCHALT", "WW", "HEIZEN+WW", "PARTY"],
        "description": "Set operating mode"
    }
}

def on_connect(client, userdata, flags, rc):
    """Callback for when the client connects to the MQTT broker."""
    if rc == 0:
        logger.info("Connected to MQTT broker")
        # Subscribe to set commands
        client.subscribe(MQTT_SET_TOPIC)
        logger.info(f"Subscribed to {MQTT_SET_TOPIC}")
    else:
        logger.error(f"Failed to connect to MQTT broker with code: {rc}")

def on_message(client, userdata, msg):
    """Callback for when a MQTT message is received."""
    try:
        # Extract command from topic (e.g., "vito/set/setTempWWsoll" -> "setTempWWsoll")
        command = msg.topic.split('/')[-1]
        
        # Check if this is a valid settable parameter
        if command not in SETTABLE_PARAMETERS:
            logger.warning(f"Received set command for unsupported parameter: {command}")
            return

        # Parse the payload
        try:
            payload = json.loads(msg.payload.decode())
            value = payload.get('value')
            if value is None:
                logger.error("No value provided in payload")
                return
        except json.JSONDecodeError as e:
            logger.error(f"Invalid payload format: {e}")
            return

        # Validate the value based on parameter type
        param_config = SETTABLE_PARAMETERS[command]
        
        if param_config['type'] == 'numeric':
            try:
                value = float(value)
                if value < param_config['min'] or value > param_config['max']:
                    logger.error(f"Value {value} is outside allowed range ({param_config['min']}-{param_config['max']}) for {command}")
                    return
            except ValueError:
                logger.error(f"Invalid numeric value: {value}")
                return
        
        elif param_config['type'] == 'enum':
            if value not in param_config['values']:
                logger.error(f"Invalid value {value} for {command}. Allowed values: {param_config['values']}")
                return

        # Execute the set command
        cmd_string = f"{command} {value}"
        result = execute_vclient_command(cmd_string)
        if result is not None:
            logger.info(f"Successfully set {command} to {value}")
            
            # Publish confirmation
            publish_command_value(client, command, param_config['description'], value)
        else:
            logger.error(f"Failed to set {command} to {value}")

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")

def clean_numeric_value(value_str):
    """Clean and format numeric value from vclient output."""
    try:
        numeric_match = re.search(r'-?\d+\.?\d*', value_str)
        if numeric_match:
            return f"{float(numeric_match.group()):.1f}"
        return None
    except (ValueError, TypeError):
        return None

def execute_vclient_command(command):
    """Execute vclient command and return the result."""
    try:
        # Construct the command
        vclient_args = ['vclient', '-h', '127.0.0.1', '-p', '3002', command]
        
        result = subprocess.run(vclient_args, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            # For get commands (containing no space), extract the value
            if ' ' not in command:
                output_parts = result.stdout.strip().split(':')
                if len(output_parts) >= 2:
                    value = clean_numeric_value(output_parts[1].strip())
                    if value is not None:
                        return value
            # For set commands, return success
            else:
                return "OK"
                
        logger.warning(f"Command {command} failed with output: {result.stdout}")
        return None
    except subprocess.TimeoutExpired:
        logger.error(f"Command {command} timed out")
        return None
    except Exception as e:
        logger.error(f"Error executing command {command}: {str(e)}")
        return None

def publish_command_value(client, command, description, value):
    """Publish command value to MQTT."""
    topic = f"{MQTT_BASE_TOPIC}/{command}"
    payload = {
        "command": command,
        "description": description,
        "value": value,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        client.publish(topic, json.dumps(payload), retain=True)
        logger.debug(f"Published {command} = {value} to {topic}")
    except Exception as e:
        logger.error(f"Error publishing to MQTT: {str(e)}")

def main():
    """Main function to run the MQTT publisher."""
    # Initialize MQTT client
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        # Connect to MQTT broker
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_start()

        # Combine all commands
        all_commands = {
            **PLAUSIBLE_COMMANDS,
            **SUSPICIOUS_COMMANDS,
            **ADDITIONAL_COMMANDS
        }
            
        while True:
            for command, description in all_commands.items():
                value = execute_vclient_command(command)
                if value is not None:
                    publish_command_value(client, command, description, value)
                time.sleep(1)  # Small delay between commands
            
            # Wait before next cycle
            logger.info("Completed one cycle, waiting before next update")
            time.sleep(10)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
