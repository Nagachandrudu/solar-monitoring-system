from flask import Flask, request, jsonify
from flask_cors import CORS
from openpyxl import Workbook, load_workbook
from datetime import datetime
import os
import statistics
import threading
import time


# Stores the latest automatic hourly analysis result
last_hourly_analysis = {
    "status": "WAITING",
    "message": "No automatic hourly analysis completed yet.",
    "analysis_time": None
}



app = Flask(__name__)
CORS(app)

# =========================================================
# CONFIGURATION
# =========================================================

EXCEL_FILE = "solar_data.xlsx"

latest_data = {
    "voltage": 0,
    "current": 0,
    "power": 0,
    "temperature": 0,
    "light": 0,
    "datetime": ""
}


# =========================================================
# CREATE EXCEL FILE
# =========================================================

def create_excel_file():

    if not os.path.exists(EXCEL_FILE):

        workbook = Workbook()

        sheet = workbook.active
        sheet.title = "Solar Data"

        sheet.append([
            "DateTime",
            "Voltage (V)",
            "Current (mA)",
            "Power (mW)",
            "Temperature (°C)",
            "Light (lux)"
        ])

        workbook.save(EXCEL_FILE)


create_excel_file()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return "Solar Monitoring Backend is Running!"


# =========================================================
# RECEIVE ESP32 DATA
# =========================================================

@app.route("/data", methods=["POST"])
def receive_data():

    global latest_data

    try:

        data = request.get_json()

        if not data:
            return jsonify({
                "status": "error",
                "message": "No JSON data received"
            }), 400

        voltage = data.get("voltage")
        current = data.get("current")
        power = data.get("power")
        temperature = data.get("temperature")
        light = data.get("light")

        # -------------------------------------------------
        # CHECK BASIC SENSOR VALUES
        # -------------------------------------------------

        if voltage is None:
            voltage = 0

        if current is None:
            current = 0

        if power is None:
            power = 0

        if temperature is None:
            temperature = None

        if light is None:
            light = 0

        # -------------------------------------------------
        # INVALID TEMPERATURE
        # DS18B20 often gives -127 when disconnected
        # -------------------------------------------------

        if temperature is not None:

            try:
                temperature = float(temperature)

                if temperature <= -50 or temperature >= 100:
                    temperature = None

            except:
                temperature = None

        current_datetime = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # -------------------------------------------------
        # UPDATE LATEST DATA
        # -------------------------------------------------

        latest_data = {
            "voltage": voltage,
            "current": current,
            "power": power,
            "temperature": temperature,
            "light": light,
            "datetime": current_datetime
        }

        # -------------------------------------------------
        # SAVE TO EXCEL
        # -------------------------------------------------

        workbook = load_workbook(EXCEL_FILE)

        if "Solar Data" not in workbook.sheetnames:

            sheet = workbook.create_sheet("Solar Data")

            sheet.append([
                "DateTime",
                "Voltage (V)",
                "Current (mA)",
                "Power (mW)",
                "Temperature (°C)",
                "Light (lux)"
            ])

        sheet = workbook["Solar Data"]

        sheet.append([
            current_datetime,
            voltage,
            current,
            power,
            temperature,
            light
        ])

        workbook.save(EXCEL_FILE)

        print()
        print("====================================")
        print("       NEW SOLAR DATA")
        print("====================================")

        print("Voltage     :", voltage, "V")
        print("Current     :", current, "mA")
        print("Power       :", power, "mW")
        print("Temperature :", temperature, "C")
        print("Light       :", light, "lux")
        print("Time        :", current_datetime)

        print("====================================")

        return jsonify({
            "status": "success",
            "message": "Data saved successfully",
            "data": latest_data
        })

    except Exception as e:

        print("ERROR:", str(e))

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# =========================================================
# LATEST DATA
# =========================================================

@app.route("/latest", methods=["GET"])
def get_latest():

    return jsonify(latest_data)





# =========================================================
# READ VALID EXCEL DATA
# =========================================================

def read_valid_data():

    if not os.path.exists(EXCEL_FILE):
        return []

    workbook = load_workbook(
        EXCEL_FILE,
        data_only=True
    )

    if "Solar Data" not in workbook.sheetnames:
        return []

    sheet = workbook["Solar Data"]

    records = []

    for row in sheet.iter_rows(min_row=2, values_only=True):

        if len(row) < 6:
            continue

        date_time = row[0]
        voltage = row[1]
        current = row[2]
        power = row[3]
        temperature = row[4]
        light = row[5]

        # -------------------------------------------------
        # CHECK NUMERIC VALUES
        # -------------------------------------------------

        try:

            voltage = float(voltage)
            current = float(current)
            power = float(power)
            light = float(light)

            if temperature is None:
                continue

            temperature = float(temperature)

        except:

            continue

        # -------------------------------------------------
        # REMOVE INVALID SENSOR VALUES
        # -------------------------------------------------

        if temperature <= -50 or temperature >= 100:
            continue

        if voltage < 0:
            continue

        if current < 0:
            continue

        if power < 0:
            continue

        if light < 0:
            continue

        records.append({
            "datetime": str(date_time),
            "voltage": voltage,
            "current": current,
            "power": power,
            "temperature": temperature,
            "light": light
        })

    return records


# =========================================================
# FIND EXPECTED POWER FROM BASELINE DATA
# =========================================================

def calculate_expected_power(light, temperature, records):

    if not records:

        return 0, "NO BASELINE"


    # -----------------------------------------------------
    # STEP 1
    # Find records having similar light intensity
    #
    # Light tolerance = approximately ±20%
    # -----------------------------------------------------

    light_tolerance = max(10, light * 0.20)

    similar_records = []

    for record in records:

        light_difference = abs(
            record["light"] - light
        )

        temperature_difference = abs(
            record["temperature"] - temperature
        )

        if (
            light_difference <= light_tolerance
            and temperature_difference <= 5
        ):

            similar_records.append(record)


    # -----------------------------------------------------
    # STEP 2
    # If not enough records, use wider light range
    # -----------------------------------------------------

    if len(similar_records) < 3:

        similar_records = []

        for record in records:

            light_difference = abs(
                record["light"] - light
            )

            if light_difference <= max(20, light * 0.40):

                similar_records.append(record)


    # -----------------------------------------------------
    # STEP 3
    # If still no data, use nearest records
    # -----------------------------------------------------

    if len(similar_records) < 3:

        sorted_records = sorted(
            records,
            key=lambda r:
            abs(r["light"] - light)
        )

        similar_records = sorted_records[:5]


    if not similar_records:

        return 0, "NO BASELINE"


    # -----------------------------------------------------
    # STEP 4
    # Use positive power values
    #
    # This avoids zero-power records dominating
    # the healthy baseline.
    # -----------------------------------------------------

    positive_powers = [
        r["power"]
        for r in similar_records
        if r["power"] > 0
    ]


    # -----------------------------------------------------
    # If all values are zero, we cannot create a
    # meaningful expected-power baseline.
    # -----------------------------------------------------

    if not positive_powers:

        return 0, "NO POSITIVE BASELINE"


    # -----------------------------------------------------
    # STEP 5
    # Use 75th percentile-like value.
    #
    # This represents better observed performance
    # under similar conditions.
    # -----------------------------------------------------

    positive_powers.sort()

    index = int(
        0.75 * (len(positive_powers) - 1)
    )

    expected_power = positive_powers[index]


    # -----------------------------------------------------
    # Temperature correction
    #
    # Small correction only.
    # -----------------------------------------------------

    temperature_difference = temperature - 32.0

    temperature_factor = 1.0 - (
        temperature_difference * 0.005
    )

    # Keep factor within safe limits

    if temperature_factor < 0.90:
        temperature_factor = 0.90

    if temperature_factor > 1.10:
        temperature_factor = 1.10


    expected_power *= temperature_factor


    return expected_power, "BASELINE"


# =========================================================
# CLASSIFY SOLAR PERFORMANCE
# =========================================================

def classify_power(actual_power, expected_power):

    # -----------------------------------------------------
    # No baseline available
    # -----------------------------------------------------

    if expected_power <= 0:

        return {
            "status": "NO BASELINE",
            "percentage": 0
        }


    percentage = (
        actual_power / expected_power
    ) * 100


    # -----------------------------------------------------
    # NORMAL
    # -----------------------------------------------------

    if percentage >= 90:

        status = "NORMAL"


    # -----------------------------------------------------
    # WARNING
    # -----------------------------------------------------

    elif percentage >= 70:

        status = "WARNING"


    # -----------------------------------------------------
    # LOW OUTPUT
    # -----------------------------------------------------

    elif percentage >= 50:

        status = "LOW OUTPUT"


    # -----------------------------------------------------
    # CRITICAL
    # -----------------------------------------------------

    else:

        status = "CRITICAL"


    return {
        "status": status,
        "percentage": round(percentage, 2)
    }

# =========================================================
# LAST AUTOMATIC HOURLY ANALYSIS
# =========================================================

@app.route("/last-hourly-analysis", methods=["GET"])
def get_last_hourly_analysis():

    return jsonify(last_hourly_analysis)




# =========================================================
# ANALYZE STORED DATA
# =========================================================

@app.route("/analyze", methods=["GET"])
def analyze_data():

    try:

        # -------------------------------------------------
        # READ VALID DATA
        # -------------------------------------------------

        records = read_valid_data()


        # -------------------------------------------------
        # COUNT TOTAL EXCEL RECORDS
        # -------------------------------------------------

        workbook = load_workbook(
            EXCEL_FILE,
            data_only=True
        )

        if "Solar Data" in workbook.sheetnames:

            sheet = workbook["Solar Data"]

            total_records = max(
                0,
                sheet.max_row - 1
            )

        else:

            total_records = 0


        invalid_temperature_records = (
            total_records - len(records)
        )


        # -------------------------------------------------
        # NO DATA
        # -------------------------------------------------

        if not records:

            return jsonify({

                "status": "success",

                "overall_status": "NO VALID DATA",

                "message":
                    "No valid solar data available.",

                "total_records":
                    total_records,

                "valid_records":
                    0,

                "invalid_temperature_records":
                    invalid_temperature_records,

                "normal": 0,

                "warning": 0,

                "low_output": 0,

                "critical": 0,

                "average_power": 0,

                "average_temperature": 0,

                "average_light": 0,

                "records": []

            })


        # -------------------------------------------------
        # AVERAGES
        # -------------------------------------------------

        average_power = statistics.mean(
            r["power"] for r in records
        )

        average_temperature = statistics.mean(
            r["temperature"] for r in records
        )

        average_light = statistics.mean(
            r["light"] for r in records
        )


        # -------------------------------------------------
        # COUNTERS
        # -------------------------------------------------

        normal_count = 0
        warning_count = 0
        low_output_count = 0
        critical_count = 0
        no_baseline_count = 0


        analysis_records = []


        # -------------------------------------------------
        # ANALYZE EVERY RECORD
        # -------------------------------------------------

        for record in records:

            expected_power, baseline_type = (
                calculate_expected_power(
                    record["light"],
                    record["temperature"],
                    records
                )
            )


            classification = classify_power(
                record["power"],
                expected_power
            )


            status = classification["status"]

            percentage = classification["percentage"]


            # -------------------------------------------------
            # COUNT STATUS
            # -------------------------------------------------

            if status == "NORMAL":

                normal_count += 1

            elif status == "WARNING":

                warning_count += 1

            elif status == "LOW OUTPUT":

                low_output_count += 1

            elif status == "CRITICAL":

                critical_count += 1

            elif status == "NO BASELINE":

                no_baseline_count += 1


            # -------------------------------------------------
            # SAVE ANALYSIS RESULT
            # -------------------------------------------------

            analysis_records.append({

                "datetime":
                    record["datetime"],

                "voltage":
                    round(record["voltage"], 2),

                "current":
                    round(record["current"], 2),

                "actual_power":
                    round(record["power"], 3),

                "temperature":
                    round(record["temperature"], 2),

                "light":
                    round(record["light"], 2),

                "expected_power":
                    round(expected_power, 3),

                "performance":
                    round(percentage, 2),

                "status":
                    status,

                "baseline":
                    baseline_type

            })


        # -------------------------------------------------
        # OVERALL SYSTEM STATUS
        # -----------------------------------------------------

        usable_status_count = (
            normal_count
            + warning_count
            + low_output_count
            + critical_count
        )


        if usable_status_count == 0:

            overall_status = "NO BASELINE"

            message = (
                "Not enough positive power data "
                "to create a performance baseline."
            )

        elif critical_count > (
            usable_status_count * 0.50
        ):

            overall_status = "CRITICAL"

            message = (
                "System producing much less power. "
                "Please check your solar system."
            )

        elif low_output_count > (
            usable_status_count * 0.30
        ):

            overall_status = "LOW OUTPUT"

            message = (
                "Solar system output is below "
                "the expected level."
            )

        elif warning_count > (
            usable_status_count * 0.30
        ):

            overall_status = "WARNING"

            message = (
                "Solar system performance needs "
                "attention."
            )

        else:

            overall_status = "NORMAL"

            message = (
                "Solar system is operating "
                "within the learned baseline."
            )


        # -------------------------------------------------
        # FINAL RESPONSE
        # -------------------------------------------------

        return jsonify({

            "status": "success",

            "overall_status":
                overall_status,

            "message":
                message,

            "total_records":
                total_records,

            "valid_records":
                len(records),

            "invalid_temperature_records":
                invalid_temperature_records,

            "normal":
                normal_count,

            "warning":
                warning_count,

            "low_output":
                low_output_count,

            "critical":
                critical_count,

            "no_baseline":
                no_baseline_count,

            "average_power":
                round(average_power, 3),

            "average_temperature":
                round(average_temperature, 2),

            "average_light":
                round(average_light, 2),

            "records":
                analysis_records

        })


    except Exception as e:

        print("ANALYSIS ERROR:", str(e))

        return jsonify({

            "status": "error",

            "message": str(e)

        }), 500



# =========================================================
# AUTOMATIC HOURLY ANALYSIS
# =========================================================

def automatic_hourly_analysis():

    while True:

        time.sleep(60)   # 1 hour

        try:
            print()
            print("====================================")
            print("     AUTOMATIC HOURLY ANALYSIS")
            print("====================================")

            with app.test_request_context("/analyze"):
                result = analyze_data()

            analysis_result = result.get_json()

            last_hourly_analysis.clear()
            last_hourly_analysis.update({
                "status": analysis_result.get("overall_status", "UNKNOWN"),
                "message": analysis_result.get(
                "message",
                "Automatic analysis completed."
                ),
                "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": analysis_result
        })

            print("Automatic analysis completed.")
            print("Result:")
            print(analysis_result)

            print("====================================")
            print()

        except Exception as e:
            print("AUTOMATIC ANALYSIS ERROR:", str(e))


# =========================================================
# RUN FLASK SERVER
# =========================================================



if __name__ == "__main__":

    print()
    print("====================================")
    print("     SOLAR MONITORING BACKEND")
    print("====================================")
    print("Server running on:")
    print("http://0.0.0.0:5000")
    print("====================================")
    print()
    analysis_thread = threading.Thread(
        target=automatic_hourly_analysis,
        daemon=True
    )

    analysis_thread.start()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )