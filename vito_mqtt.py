#!/usr/bin/env python3
import subprocess
import json
import paho.mqtt.client as mqtt
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# MQTT Configuration
MQTT_HOST = "10.0.1.8"
MQTT_PORT = 1883
MQTT_BASE_TOPIC = "vito"

# Dictionary of commands and their English translations
PLAUSIBLE_COMMANDS = {
    "getStatusQuellePri1": "Primary source status",
    "getAnzQuelleSek": "Secondary source count",
    "getAnzHeizstabSt1": "Heating rod stage 1 count",
    "getAnzHeizstabSt2": "Heating rod stage 2 count",
    "getAnzHK": "Heating circuit count",
    "getStatusZirkPumpe": "Circulation pump status",
    "getStatusVerdichter": "Compressor status",
    "getStatusVentilWW": "DHW valve status",
    "getEHeizungStufe1BS": "E-heating stage 1 status",
    "getEHeizungStufe2BS": "E-heating stage 2 status",
    "getHK1PumpeBS": "Heating circuit 1 pump status",
    "getVerdichter1BS": "Compressor 1 status",
    "getVerdichter2BS": "Compressor 2 status",
    "getVorlaufTemp1": "Supply temperature 1",
    "getRuecklaufTemp1": "Return temperature 1",
    "getEEV1": "Electronic expansion valve 1",
    "getTempA": "Outside temperature",
    "getTempWWObenIst": "Current DHW top temperature",
    "getTempWWUntenIst": "Current DHW bottom temperature",
    "getTempWWsoll": "Hot water setpoint temperature",
    "getWWBereitung": "DHW preparation status",
    "getTempStp2": "DHW outlet temperature",
    "getNeigungHK1": "Heating curve slope (HK1)",
    "getNeigungHK2": "Heating curve slope (HK2)",
    "getNiveauHK1": "Heating curve level (HK1)",
    "getNiveauHK2": "Heating curve level (HK2)",
    "getTempVL": "Supply temperature",
    "getTempRL": "Return temperature",
    "getTempVListHK1": "Supply temperature HK1",
    "getTempRListHK1": "Return temperature HK1",
    "getTempVLsollM2": "Supply setpoint temperature for M2",
    "getTempRL17A": "Return temperature 17A",
    "getTempSpu": "Storage bottom temperature",
    "getTempStp": "Storage temperature (low-pass)",
    "getLZSNH": "Operating hours counter",
    "getLZAC": "Operating hours AC",
    "getLZPumpe": "Operating hours pump",
    "getLZWP": "Operating hours heat pump",
    "getPumpeStatusSp": "Storage charging pump status",
    "getPumpeStatusZirku": "Recirculation pump status",
    "getTempSTSSOL": "Tank temperature (solar low-pass)",
    "getMischerM1": "Mixing valve position M1",
    "getMischerM2": "Mixing valve position M2",
    "getMischerM3": "Mixing valve position M3",
    "getBetriebArtHK1": "Operating mode HK1",
    "getBetriebArtHK2": "Operating mode HK2",
    "getJAZ": "Annual performance factor",
    "getJAZHeiz": "Heating annual performance",
    "getJAZWW": "DHW annual performance",
    "getTimerWWMo": "Monday DHW schedule",
    "getInventory": "Part number",
    "getInvCodePlug": "Part number of coding plug",    
    "getStatusVentilatorstufe1": "ABC",
    "getStatusVentilatorstufe2": "ABC",
    "getRaumtemperaturIst": "ABC",
    "getBetriebsstdVerdichter": "ABC",
    "getBetriebsstdVentilatorstufe1": "ABC",
    "getEinschaltVerdichter": "ABC",
    "getEinschaltPrimaerquelle": "ABC",
    "getJAZWW": "ABC",
    "getCOPHeizen": "ABC",
    "getHeizleistung": "ABC",
    "getLeistungsaufnahme": "ABC",
    "getAussentemperatur1": "ABC",
    "getRaum": "ABC",
    "getRaum2": "ABC"
}

SUSPICIOUS_COMMANDS = {
    "getWWUWPNachlauf": "DHW pump post-run time",
    "getSpeichervorrang": "Priority storage for heating circuit A1/M1",
    "getSpeichervorrangM2": "Priority storage for heating circuit M2",
    "getSpeichervorrangM3": "Priority storage for heating circuit M3",
    "getTempRaumNorSollM1": "Normal room setpoint temperature M1",
    "getTempRaumNorSollM2": "Normal room setpoint temperature M2",
    "getTempRaumRedSollM1": "Reduced room setpoint temperature M1",
    "getTempRaumRedSollM2": "Reduced room setpoint temperature M2",
    "getTempPartyHK1": "Party mode setpoint temperature HK1",
    "getTempPartyHK2": "Party mode setpoint temperature HK2",
    "getEinflussExtSperren": "External blocking influence on pumps",
    "getEinflussExtAnforderung": "External demand influence on pumps",
    "getStatusFrostM1": "Frost warning status M1",
    "getStatusFrostM2": "Frost warning status M2",
    "getSystemTime": "System controller time",
    "getKA5": "Heating circuit pump logic",
    "getKA5M2": "Heating circuit pump logic M2",
    "getKA5M3": "Heating circuit pump logic M3",
    "getKA6": "Absolute summer-saving mode",
    "getKA6M2": "Absolute summer-saving mode M2",
    "getKA6M3": "Absolute summer-saving mode M3",
    "getKonfiWirkung_aufPumpe": "Mixer influence on internal pump",
    "getKA3_KonfiFrostgrenzeM1_GWG": "Frost limit A1M1",
    "getKA3_KonfiFrostgrenzeM2_GWG": "Frost limit M2",
    "getDevType": "Device type/System identification",
    "getCtrlId": "Controller identification",
    "getPanelSWIndex": "Control panel software index",
    "getKsCardType": "KS card type",
    "getAnlagenschema": "System layout",
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
    "getEnergieElektroWW12M": "Electrical energy for DHW (12 months)",
    "getEnergieWaermeWW12M": "Thermal energy for DHW (12 months)",
    "getEnergieElektroHeizen12M": "Electrical energy for heating (12 months)",
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
    "getHeizleistung": "Heating output (kW or similar unit)",
    "getLeistungsaufnahme": "Power consumption (kW or similar unit)",
    "getEingangstemperaturLuft": "Average inlet air temperature",
    "getAusgangstemperaturLuft": "Average outlet air temperature",
    "getCOPWW": "COP for domestic hot water",
    "getCOPHeizen": "COP for heating",
    "getDruckVerdampfer": "Evaporator pressure",
    "getDruckKondensator": "Condenser pressure",
    "getFreigabeElektroWW": "Enable electric heater for DHW",
    "getFreigabeHeizElektro": "Enable electric heater for space heating",
    "getFreigabeDurchlauferh": "Enable instantaneous water heater for heating",
    "getStatusVentilatorstufe1": "Fan stage 1 status",
    "getStatusVentilatorstufe2": "Fan stage 2 status",
    "getStatusKaeltekreisumkehr": "Refrigerant circuit reversal status",
    "getAussentemperaturRegelung": "Outdoor temperature (for controller)",
    "getAussentemperatur1": "Outdoor temperature sensor 1",
    "getAussentemperatur2": "Outdoor temperature sensor 2",
    "getAussentemperatur3": "Outdoor temperature sensor 3",
    "getAussentemperatur4": "Outdoor temperature sensor 4",
    "getAussentemperatur5": "Outdoor temperature sensor 5",
    "getRaumtemperaturIST": "Room temperature (Vitotrol HK1)",
    "getRaumtemperaturParty": "Party-mode room temperature (Heating Circuit A1/HK1)",
    "getJAZgesamt": "Seasonal performance factor (overall)",
    "getJAZHeizen": "Seasonal performance factor (heating)",
    "getJAZWW": "Seasonal performance factor (domestic hot water)"
}



def on_connect(client, userdata, flags, rc):
    """Callback for when the client connects to the MQTT broker."""
    if rc == 0:
        logger.info("Connected to MQTT broker")
    else:
        logger.error(f"Failed to connect to MQTT broker with code: {rc}")

def clean_numeric_value(value_str):
    """Clean and format numeric value from vclient output."""
    try:
        # Remove any text and keep only the first number found
        import re
        numeric_match = re.search(r'-?\d+\.?\d*', value_str)
        if numeric_match:
            # Convert to float and format to one decimal place
            return f"{float(numeric_match.group()):.1f}"
        return None
    except (ValueError, TypeError):
        return None

def execute_vclient_command(command):
    """Execute vclient command and return the result."""
    try:
        result = subprocess.run(['vclient', '-h', '127.0.0.1', '-p', '3002', '-c', command],
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            # Extract the value from the output
            output_parts = result.stdout.strip().split(':')
            if len(output_parts) >= 2:
                value = clean_numeric_value(output_parts[1].strip())
                if value is not None:
                    return value
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

    try:
        # Connect to MQTT broker
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_start()

        # Process all commands
        # Add the newly created dictionary
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
            
            # Wait before next cycle (5 minutes)
            logger.info("Completed one cycle, waiting 5 minutes before next update")
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