from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime
import statistics
import os

from supabase_client import supabase


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)
CORS(app)


# =========================================================
# LATEST DATA
# =========================================================

latest_data = {
    "voltage": 0,
    "current": 0,
    "power": 0,
    "temperature": 0,
    "light": 0,
    "datetime": ""
}


# =========================================================
# LAST AUTOMATIC HOURLY ANALYSIS
# =========================================================

last_hourly_analysis = {
    "status": "WAITING",
    "message": "No automatic hourly analysis completed yet.",
    "analysis_time": None,
    "data": None
}


# =========================================================
# HOME / DASHBOARD
# =========================================================

@app.route("/")
def home():

    return send_from_directory(
        os.path.dirname(os.path.abspath(__file__)),
        "index.html"
    )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "status": "online",
        "message": "Solar Monitoring Backend is running."
    })


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


        # -------------------------------------------------
        # GET SENSOR VALUES
        # -------------------------------------------------

        voltage = data.get("voltage", 0)
        current = data.get("current", 0)
        power = data.get("power", 0)
        temperature = data.get("temperature")
        light = data.get("light", 0)


        # -------------------------------------------------
        # CONVERT NUMERIC VALUES
        # -------------------------------------------------

        try:
            voltage = float(voltage)
        except:
            voltage = 0


        try:
            current = float(current)
        except:
            current = 0


        try:
            power = float(power)
        except:
            power = 0


        try:
            light = float(light)
        except:
            light = 0


        # -------------------------------------------------
        # TEMPERATURE VALIDATION
        # -------------------------------------------------

        if temperature is not None:

            try:

                temperature = float(temperature)

                # DS18B20 disconnected / invalid reading
                if temperature <= -50 or temperature >= 100:

                    temperature = None

            except:

                temperature = None


        # -------------------------------------------------
        # PREVENT NEGATIVE VALUES
        # -------------------------------------------------

        if voltage < 0:
            voltage = 0

        if current < 0:
            current = 0

        if power < 0:
            power = 0

        if light < 0:
            light = 0


        # -------------------------------------------------
        # CURRENT TIME
        # -------------------------------------------------

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


        # =================================================
        # SAVE DATA TO SUPABASE
        # =================================================

        supabase_data = {

            "voltage": voltage,

            "current": current,

            "power": power,

            "temperature": temperature,

            "light": light
        }


        result = supabase.table(
            "solar_data"
        ).insert(
            supabase_data
        ).execute()


        # -------------------------------------------------
        # PRINT DATA
        # -------------------------------------------------

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

        print("Saved to    : Supabase")

        print("====================================")


        return jsonify({

            "status": "success",

            "message": "Data saved successfully to Supabase",

            "data": latest_data
        })


    except Exception as e:

        print("SUPABASE DATA ERROR:", str(e))

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
# READ VALID DATA FROM SUPABASE
# =========================================================

def read_valid_data():

    try:

        result = supabase.table(
            "solar_data"
        ).select(
            "*"
        ).order(
            "created_at",
            desc=False
        ).execute()


        rows = result.data or []

        records = []


        for row in rows:

            try:

                voltage = float(
                    row.get("voltage", 0)
                )

                current = float(
                    row.get("current", 0)
                )

                power = float(
                    row.get("power", 0)
                )

                light = float(
                    row.get("light", 0)
                )

                temperature = row.get(
                    "temperature"
                )


                if temperature is None:
                    continue


                temperature = float(
                    temperature
                )


            except:

                continue


            # -------------------------------------------------
            # INVALID VALUES
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


            # -------------------------------------------------
            # DATETIME
            # -------------------------------------------------

            date_time = row.get(
                "created_at",
                ""
            )


            records.append({

                "datetime": str(date_time),

                "voltage": voltage,

                "current": current,

                "power": power,

                "temperature": temperature,

                "light": light
            })


        return records


    except Exception as e:

        print(
            "SUPABASE READ ERROR:",
            str(e)
        )

        return []


# =========================================================
# FIND EXPECTED POWER FROM BASELINE DATA
# =========================================================

def calculate_expected_power(
    light,
    temperature,
    records
):

    if not records:

        return 0, "NO BASELINE"


    # -----------------------------------------------------
    # STEP 1
    # Similar light and temperature
    # -----------------------------------------------------

    light_tolerance = max(
        10,
        light * 0.20
    )


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

            and

            temperature_difference <= 5

        ):

            similar_records.append(
                record
            )


    # -----------------------------------------------------
    # STEP 2
    # Wider light range
    # -----------------------------------------------------

    if len(similar_records) < 3:

        similar_records = []


        for record in records:

            light_difference = abs(
                record["light"] - light
            )


            if light_difference <= max(
                20,
                light * 0.40
            ):

                similar_records.append(
                    record
                )


    # -----------------------------------------------------
    # STEP 3
    # Nearest records
    # -----------------------------------------------------

    if len(similar_records) < 3:

        sorted_records = sorted(

            records,

            key=lambda r:
                abs(r["light"] - light)

        )


        similar_records = (
            sorted_records[:5]
        )


    if not similar_records:

        return 0, "NO BASELINE"


    # -----------------------------------------------------
    # STEP 4
    # POSITIVE POWER VALUES
    # -----------------------------------------------------

    positive_powers = [

        r["power"]

        for r in similar_records

        if r["power"] > 0

    ]


    if not positive_powers:

        return 0, "NO POSITIVE BASELINE"


    # -----------------------------------------------------
    # STEP 5
    # 75th percentile-like value
    # -----------------------------------------------------

    positive_powers.sort()


    index = int(

        0.75 *
        (len(positive_powers) - 1)

    )


    expected_power = (
        positive_powers[index]
    )


    # -----------------------------------------------------
    # TEMPERATURE CORRECTION
    # -----------------------------------------------------

    temperature_difference = (
        temperature - 32.0
    )


    temperature_factor = (
        1.0 -
        (
            temperature_difference
            * 0.005
        )
    )


    if temperature_factor < 0.90:

        temperature_factor = 0.90


    if temperature_factor > 1.10:

        temperature_factor = 1.10


    expected_power *= (
        temperature_factor
    )


    return (
        expected_power,
        "BASELINE"
    )


# =========================================================
# CLASSIFY SOLAR PERFORMANCE
# =========================================================

def classify_power(
    actual_power,
    expected_power
):

    if expected_power <= 0:

        return {

            "status":
                "NO BASELINE",

            "percentage":
                0
        }


    percentage = (

        actual_power /
        expected_power

    ) * 100


    if percentage >= 90:

        status = "NORMAL"


    elif percentage >= 70:

        status = "WARNING"


    elif percentage >= 50:

        status = "LOW OUTPUT"


    else:

        status = "CRITICAL"


    return {

        "status":
            status,

        "percentage":
            round(
                percentage,
                2
            )
    }


# =========================================================
# ANALYZE STORED DATA
# =========================================================

@app.route(
    "/analyze",
    methods=["GET"]
)
def analyze_data():

    try:

        # -------------------------------------------------
        # READ SUPABASE DATA
        # -------------------------------------------------

        records = read_valid_data()


        # -------------------------------------------------
        # TOTAL RECORDS
        # -------------------------------------------------

        try:

            count_result = (
                supabase
                .table("solar_data")
                .select(
                    "id",
                    count="exact"
                )
                .execute()
            )


            total_records = (
                count_result.count
                if count_result.count is not None
                else len(records)
            )


        except:

            total_records = len(
                records
            )


        # -------------------------------------------------
        # INVALID RECORDS
        # -------------------------------------------------

        invalid_temperature_records = (

            total_records -
            len(records)

        )


        # -------------------------------------------------
        # NO DATA
        # -------------------------------------------------

        if not records:

            return jsonify({

                "status":
                    "success",

                "overall_status":
                    "NO VALID DATA",

                "message":
                    "No valid solar data available.",

                "total_records":
                    total_records,

                "valid_records":
                    0,

                "invalid_temperature_records":
                    invalid_temperature_records,

                "normal":
                    0,

                "warning":
                    0,

                "low_output":
                    0,

                "critical":
                    0,

                "average_power":
                    0,

                "average_temperature":
                    0,

                "average_light":
                    0,

                "records":
                    []

            })


        # -------------------------------------------------
        # AVERAGES
        # -------------------------------------------------

        average_power = statistics.mean(

            r["power"]

            for r in records

        )


        average_temperature = statistics.mean(

            r["temperature"]

            for r in records

        )


        average_light = statistics.mean(

            r["light"]

            for r in records

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


            status = classification[
                "status"
            ]


            percentage = classification[
                "percentage"
            ]


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
                    round(
                        record["voltage"],
                        2
                    ),

                "current":
                    round(
                        record["current"],
                        2
                    ),

                "actual_power":
                    round(
                        record["power"],
                        3
                    ),

                "temperature":
                    round(
                        record["temperature"],
                        2
                    ),

                "light":
                    round(
                        record["light"],
                        2
                    ),

                "expected_power":
                    round(
                        expected_power,
                        3
                    ),

                "performance":
                    round(
                        percentage,
                        2
                    ),

                "status":
                    status,

                "baseline":
                    baseline_type
            })


        # -------------------------------------------------
        # OVERALL STATUS
        # -------------------------------------------------

        usable_status_count = (

            normal_count

            + warning_count

            + low_output_count

            + critical_count

        )


        if usable_status_count == 0:

            overall_status = (
                "NO BASELINE"
            )

            message = (
                "Not enough positive power "
                "data to create a performance "
                "baseline."
            )


        elif critical_count > (

            usable_status_count * 0.50

        ):

            overall_status = (
                "CRITICAL"
            )

            message = (
                "System producing much less "
                "power. Please check your "
                "solar system."
            )


        elif low_output_count > (

            usable_status_count * 0.30

        ):

            overall_status = (
                "LOW OUTPUT"
            )

            message = (
                "Solar system output is below "
                "the expected level."
            )


        elif warning_count > (

            usable_status_count * 0.30

        ):

            overall_status = (
                "WARNING"
            )

            message = (
                "Solar system performance needs "
                "attention."
            )


        else:

            overall_status = (
                "NORMAL"
            )

            message = (
                "Solar system is operating "
                "within the learned baseline."
            )


        # -------------------------------------------------
        # FINAL RESULT
        # -------------------------------------------------

        return jsonify({

            "status":
                "success",

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
                round(
                    average_power,
                    3
                ),

            "average_temperature":
                round(
                    average_temperature,
                    2
                ),

            "average_light":
                round(
                    average_light,
                    2
                ),

            "records":
                analysis_records

        })


    except Exception as e:

        print(
            "ANALYSIS ERROR:",
            str(e)
        )


        return jsonify({

            "status":
                "error",

            "message":
                str(e)

        }), 500


# =========================================================
# LAST AUTOMATIC HOURLY ANALYSIS
# =========================================================

@app.route(
    "/last-hourly-analysis",
    methods=["GET"]
)
def get_last_hourly_analysis():

    return jsonify(
        last_hourly_analysis
    )


# =========================================================
# UPDATE LAST HOURLY ANALYSIS
#
# This endpoint is intentionally provided for the
# future Render Cron Job.
# =========================================================

@app.route(
    "/run-hourly-analysis",
    methods=["GET"]
)
def run_hourly_analysis():

    global last_hourly_analysis

    try:

        with app.test_request_context(
            "/analyze"
        ):

            result = analyze_data()


        analysis_result = (
            result.get_json()
        )


        last_hourly_analysis = {

            "status":
                analysis_result.get(
                    "overall_status",
                    "UNKNOWN"
                ),

            "message":
                analysis_result.get(
                    "message",
                    "Automatic analysis completed."
                ),

            "analysis_time":
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),

            "data":
                analysis_result

        }


        print()
        print(
            "===================================="
        )
        print(
            "     HOURLY ANALYSIS COMPLETED"
        )
        print(
            "===================================="
        )

        print(
            analysis_result
        )

        print(
            "===================================="
        )
        print()


        return jsonify(
            last_hourly_analysis
        )


    except Exception as e:

        print(
            "HOURLY ANALYSIS ERROR:",
            str(e)
        )


        return jsonify({

            "status":
                "error",

            "message":
                str(e)

        }), 500


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    print()
    print(
        "===================================="
    )
    print(
        "     SOLAR MONITORING BACKEND"
    )
    print(
        "===================================="
    )
    print(
        "Server running on port 5000"
    )
    print(
        "===================================="
    )
    print()


    app.run(

        host="0.0.0.0",

        port=5000,

        debug=False

    )
