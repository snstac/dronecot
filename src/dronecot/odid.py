# (c) Bluemark Innovations BV
# MIT license

# OpenDroneID functions
from bitstruct import *
from enum import Enum
import datetime
import struct

#define MAVLink messages types
class ODID_MESSAGETYPE(Enum):
    ODID_MESSAGETYPE_BASIC_ID = 0
    ODID_MESSAGETYPE_LOCATION = 1
    ODID_MESSAGETYPE_AUTH = 2
    ODID_MESSAGETYPE_SELF_ID = 3
    ODID_MESSAGETYPE_SYSTEM = 4
    ODID_MESSAGETYPE_OPERATOR_ID = 5
    ODID_MESSAGETYPE_PACKED = 0xF

ODID_ID_SIZE = 20
ODID_STR_SIZE = 23
ODID_MESSAGE_SIZE = 25

def message_pack_to_dict(payload, size):
    """Parse an OpenDroneID message pack into a flat schema dict."""
    out = {}
    messages = []

    for x in range(size):
        start = x * ODID_MESSAGE_SIZE
        msg_payload = payload[start:start + ODID_MESSAGE_SIZE]
        rid_type = msg_payload[0] >> 4
        proto_version = msg_payload[0] & 0x0F
        message = {
            "rid_type": rid_type,
            "proto_version": proto_version,
            "raw_hex": bytes(msg_payload).hex(),
        }

        if ODID_MESSAGETYPE(rid_type) == ODID_MESSAGETYPE.ODID_MESSAGETYPE_BASIC_ID:
            message["type"] = "BASIC_ID"
            content = basicID_to_schema(msg_payload)
            message["content"] = content
            out.update(content)
        elif ODID_MESSAGETYPE(rid_type) == ODID_MESSAGETYPE.ODID_MESSAGETYPE_LOCATION:
            message["type"] = "LOCATION"
            content = location_to_schema(msg_payload)
            message["content"] = content
            out.update(content)
        elif ODID_MESSAGETYPE(rid_type) == ODID_MESSAGETYPE.ODID_MESSAGETYPE_AUTH:
            message["type"] = "AUTH"
            message["content"] = {"note": "todo"}
        elif ODID_MESSAGETYPE(rid_type) == ODID_MESSAGETYPE.ODID_MESSAGETYPE_SELF_ID:
            message["type"] = "SELF_ID"
            content = selfID_to_schema(msg_payload)
            message["content"] = content
            out.update(content)
        elif ODID_MESSAGETYPE(rid_type) == ODID_MESSAGETYPE.ODID_MESSAGETYPE_SYSTEM:
            message["type"] = "SYSTEM"
            content = system_to_schema(msg_payload)
            message["content"] = content
            out.update(content)
        elif ODID_MESSAGETYPE(rid_type) == ODID_MESSAGETYPE.ODID_MESSAGETYPE_OPERATOR_ID:
            message["type"] = "OPERATOR_ID"
            content = operatorID_to_schema(msg_payload)
            message["content"] = content
            out.update(content)
        else:
            message["type"] = "UNKNOWN"
            message["content"] = {}

        messages.append(message)

    # Extension field to keep raw per-message context without changing the flat schema.
    out["_messages"] = messages
    out["_msg_pack_size"] = size
    return out

def print_message_pack(payload, size):

	for x in range(size):
		RIDtype = payload[x*ODID_MESSAGE_SIZE] >> 4
		ProtoVersion = payload[x*ODID_MESSAGE_SIZE] & 0x0F
		if (ODID_MESSAGETYPE(RIDtype) == ODID_MESSAGETYPE.ODID_MESSAGETYPE_BASIC_ID):
			print("\n===BasicID===")
			print("RID Type: %i" % RIDtype)
			print("Proto Version: %i" % ProtoVersion)
			print_basicID(payload[x*ODID_MESSAGE_SIZE:x*ODID_MESSAGE_SIZE + ODID_MESSAGE_SIZE])

		if (ODID_MESSAGETYPE(RIDtype) == ODID_MESSAGETYPE.ODID_MESSAGETYPE_LOCATION):
			print("\n===Location===")
			print("RID Type: %i" % RIDtype)
			print("Proto Version: %i" % ProtoVersion)
			print_location(payload[x*ODID_MESSAGE_SIZE:x*ODID_MESSAGE_SIZE + ODID_MESSAGE_SIZE])

		if (ODID_MESSAGETYPE(RIDtype) == ODID_MESSAGETYPE.ODID_MESSAGETYPE_AUTH):
			print("\n===Auth===")
			print("RID Type: %i" % RIDtype)
			print("Proto Version: %i" % ProtoVersion)
			print_auth(payload[x*ODID_MESSAGE_SIZE:x*ODID_MESSAGE_SIZE + ODID_MESSAGE_SIZE])

		if (ODID_MESSAGETYPE(RIDtype) == ODID_MESSAGETYPE.ODID_MESSAGETYPE_SELF_ID):
			print("\n===SelfID===")
			print("RID Type: %i" % RIDtype)
			print("Proto Version: %i" % ProtoVersion)
			print_selfID(payload[x*ODID_MESSAGE_SIZE:x*ODID_MESSAGE_SIZE + ODID_MESSAGE_SIZE])

		if (ODID_MESSAGETYPE(RIDtype) == ODID_MESSAGETYPE.ODID_MESSAGETYPE_SYSTEM):
			print("\n===System===")
			print("RID Type: %i" % RIDtype)
			print("Proto Version: %i" % ProtoVersion)
			print_system(payload[x*ODID_MESSAGE_SIZE:x*ODID_MESSAGE_SIZE + ODID_MESSAGE_SIZE])

		if (ODID_MESSAGETYPE(RIDtype) == ODID_MESSAGETYPE.ODID_MESSAGETYPE_OPERATOR_ID):
			print("\n===OperatorID===")
			print("RID Type: %i" % RIDtype)
			print("Proto Version: %i" % ProtoVersion)
			print_operatorID(payload[x*ODID_MESSAGE_SIZE:x*ODID_MESSAGE_SIZE + ODID_MESSAGE_SIZE])

def basicID_to_schema(payload):
	IDType = payload[1] >> 4
	UAType = payload[1] & 0x0F
	UASID = payload[2:2 + ODID_ID_SIZE]
	return {
		"IDType": IDType,
		"UAType": UAType,
		"UASID": clean_SN(bytes(UASID).decode('ascii'))
	}

def location_to_schema(payload):
	Status = (payload[1] >> 4) & 0x0F
	SpeedMult = payload[1] & 0x01
	HeightType = (payload[1] >> 2) & 0x01
	Direction = float(payload[2])
	if Direction > 360 or Direction < 0:
		Direction = float('NaN')
	SpeedHorizontal = payload[3]
	SpeedVertical = int(payload[4])*0.5
	if SpeedVertical == 63:
		SpeedVertical = float('NaN')
	Latitude = int(struct.unpack('i', bytes(payload)[5:9])[0])
	Longitude = int(struct.unpack('i', bytes(payload)[9:13])[0])
	AltitudeBaro = struct.unpack('H', bytes(payload)[13:15])
	AltitudeGeo = struct.unpack('H', bytes(payload)[15:17])
	Height = struct.unpack('H', bytes(payload)[17:19])
	HorizAccuracy = payload[19] & 0x0F
	VertAccuracy = (payload[19] >> 4)& 0x0F
	BaroAccuracy = (payload[20] >> 4)& 0x0F
	SpeedAccuracy = payload[20] & 0x0F
	TimeStamp = struct.unpack('<H', bytes(payload[21:23]))[0]
	TSAccuracy = payload[23] & 0x0F

	AltitudeBaroVal = (int(AltitudeBaro[0]) - int(2000))/2
	if AltitudeBaroVal <= -1000.0 or AltitudeBaroVal > 31767.5:
		AltitudeBaroVal = float('NaN')
	AltitudeGeoVal = (int(AltitudeGeo[0]) - int(2000))/2
	if AltitudeGeoVal <= -1000.0 or AltitudeGeoVal > 31767.5:
		AltitudeGeoVal = float('NaN')
	HeightVal = (int(Height[0]) - int(2000))/2
	if HeightVal <= -1000.0 or HeightVal > 31767.5:
		HeightVal = float('NaN')

	return {
		"Status": Status,
		"Direction": Direction,
		"SpeedHorizontal": location_decode_speed_horizontal(SpeedHorizontal, SpeedMult),
		"SpeedVertical": SpeedVertical,
		"Latitude": float(Latitude)/(10*1000*1000),
		"Longitude": float(Longitude)/(10*1000*1000),
		"AltitudeBaro": AltitudeBaroVal,
		"AltitudeGeo": AltitudeGeoVal,
		"HeightType": HeightType,
		"Height": HeightVal,
		"HorizAccuracy": int(HorizAccuracy),
		"VertAccuracy": int(VertAccuracy),
		"BaroAccuracy": int(BaroAccuracy),
		"SpeedAccuracy": int(SpeedAccuracy),
		"TSAccuracy": int(TSAccuracy),
		"TimestampLocation": decode_location_timestamp((TimeStamp,)),
	}

def auth_to_dict(payload):
	return {"note": "todo"}

def selfID_to_schema(payload):
	selfID_type = payload[1]
	selfID_text = payload[2:2 + ODID_STR_SIZE]
	return {
		"DescType": selfID_type,
		"Desc": clean_string(bytes(selfID_text).decode('ascii'))
	}

def system_to_schema(payload):
	flags = payload[1]
	classification_type = (flags >> 2) & 0x03
	operator_location_type = flags & 0x03
	OperatorLatitude = int(struct.unpack('i', bytes(payload)[2:6])[0])
	OperatorLongitude = int(struct.unpack('i', bytes(payload)[6:10])[0])
	AreaCount = struct.unpack('<H', bytes(payload[10:12]))[0]
	AreaRadius = int(payload[12])
	AreaCeiling = struct.unpack('<h', bytes(payload[13:15]))
	AreaFloor = struct.unpack('<h', bytes(payload[15:17]))
	UA_category = (payload[17] >> 4) & 0x0F
	UA_class = payload[17] & 0x0F
	OperatordAltitude = struct.unpack('<h', bytes(payload)[18:20])
	TimeStamp = struct.unpack('<I', bytes(payload[20:24]))[0]

	OperatorLatitudeVal = float(OperatorLatitude)/(10*1000*1000)
	if OperatorLatitudeVal == 0.0 or OperatorLatitudeVal > 90.0 or OperatorLatitudeVal < -90.0:
		OperatorLatitudeVal = float('NaN')
	OperatorLongitudeVal = float(OperatorLongitude)/(10*1000*1000)
	if OperatorLongitudeVal == 0.0 or OperatorLongitudeVal > 180.0 or OperatorLongitudeVal < -180.0:
		OperatorLongitudeVal = float('NaN')
	AreaCeilingVal = (int(AreaCeiling[0]) - int(2000))/2
	if AreaCeilingVal == -1000:
		AreaCeilingVal = float('NaN')
	AreaFloorVal = (int(AreaFloor[0]) - int(2000))/2
	if AreaFloorVal == -1000:
		AreaFloorVal = float('NaN')
	OperatorAltitudeGeoVal = (int(OperatordAltitude[0]) - int(2000))/2
	if OperatorAltitudeGeoVal <= -1000.0 or OperatorAltitudeGeoVal > 31767.5:
		OperatorAltitudeGeoVal = float('NaN')

	return {
		"ClassificationType": classification_type,
		"OperatorLocationType": operator_location_type,
		"OperatorLatitude": OperatorLatitudeVal,
		"OperatorLongitude": OperatorLongitudeVal,
		"AreaCount": AreaCount,
		"AreaRadius": AreaRadius,
		"AreaCeiling": AreaCeilingVal,
		"AreaFloor": AreaFloorVal,
		"CategoryEU": UA_category,
		"ClassEU": UA_class,
		"OperatorAltitudeGeo": OperatorAltitudeGeoVal,
		"TimestampRaw": TimeStamp,
		"Timestamp": (decode_system_timestamp((TimeStamp,)),) if TimeStamp != 0 else (),
	}

def operatorID_to_schema(payload):
	operatorID_type = payload[1]
	operatorID = payload[2:2 + ODID_ID_SIZE]
	return {
		"OperatorIdType": operatorID_type,
		"OperatorID": clean_string(bytes(operatorID).decode('ascii'))
	}

def print_basicID(payload):
	IDType = payload[1] >> 4
	UAType = payload[1] & 0x0F
	UASID = payload[2:2 + ODID_ID_SIZE]

	print("UAType: %s" % decode_basicID_UA_type(UAType))
	print("IDType: %s" % decode_basicID_ID_type(IDType))
	print("UASID: %s" % clean_SN(bytes(UASID).decode('ascii')))

def print_location(payload):
	Status = (payload[1] >> 4) & 0x0F
	SpeedMult = payload[1] & 0x01
	EWDirection = (payload[1] >> 1) & 0x01
	HeightType = (payload[1] >> 2) & 0x01
	Direction = payload[2]
	SpeedHorizontal = payload[3]
	SpeedVertical = int(payload[4])*0.5
	if SpeedVertical == 63:
		SpeedVertical = float('NaN')

	Latitude = int(struct.unpack('i', bytes(payload)[5:9])[0])
	Longitude = int(struct.unpack('i', bytes(payload)[9:13])[0])
	AltitudeBaro = struct.unpack('H', bytes(payload)[13:15])
	AltitudeGeo = struct.unpack('H', bytes(payload)[15:17])
	Height = struct.unpack('H', bytes(payload)[17:19])
	HorizAccuracy = payload[19] & 0x0F
	VertAccuracy = (payload[19] >> 4)& 0x0F
	BaroAccuracy = (payload[20] >> 4)& 0x0F
	SpeedAccuracy = payload[20] & 0x0F
	TimeStamp = struct.unpack('<H', bytes(payload[21:23]))
	TSAccuracy = payload[23] & 0x0F

	print("Status: %s" % decode_location_status(Status))
	print("Speed Mult: %i" % SpeedMult)
	print("EW Direction: %i" % EWDirection)
	print("Height Type: %s" % decode_location_height_type(HeightType))
	print("Direction: %i" % Direction)
	print("Speed Horizontal: %2.1f" % location_decode_speed_horizontal(SpeedHorizontal, SpeedMult))
	print("Speed Vertical: %2.1f" % SpeedVertical)
	print("Latitude: %2.7f" % (float(Latitude)/(10*1000*1000)))
	print("Longitude: %2.7f" % (float(Longitude)/(10*1000*1000)))
	print("Altitude Baro: %2.1f" % ((int(AltitudeBaro[0]) - int(2000))/2))
	print("Altitude Geo: %2.1f" % ((int(AltitudeGeo[0]) - int(2000))/2))
	print("Height: %2.1f" % ((int(Height[0]) - int(2000))/2))
	print("Horiz Accuracy: %i" % int(HorizAccuracy))
	print("Vert Accuracy: %i" % int(VertAccuracy))
	print("Speed Accuracy: %i" % int(SpeedAccuracy))
	print("Timestamp: %s" % decode_location_timestamp(TimeStamp))
	print("Timestamp Accuracy: %i" % int(TSAccuracy))

def print_auth(payload):
	#todo
	print("todo")

def print_selfID(payload):
	selfID_type = payload[1]
	selfID_text = payload[2:2 + ODID_STR_SIZE]

	print("Type: %s" % decode_selfID_type(selfID_type))
	print("Text: %s" % clean_string(bytes(selfID_text).decode('ascii')))

def print_system(payload):
	flags = payload[1]
	classification_type = (flags >> 2) & 0x03
	operator_location_type = flags & 0x03
	OperatorLatitude = int(struct.unpack('i', bytes(payload)[2:6])[0])
	OperatorLongitude = int(struct.unpack('i', bytes(payload)[6:10])[0])
	AreaCount = struct.unpack('<H', bytes(payload[10:12]))[0]
	AreaRadius = int(payload[12])
	AreaCeiling = struct.unpack('<h', bytes(payload[13:15]))
	AreaFloor = struct.unpack('<h', bytes(payload[15:17]))
	UA_category = (payload[17] >> 4) & 0x0F
	UA_class = payload[17] & 0x0F
	OperatordAltitude = struct.unpack('<h', bytes(payload)[18:20])
	TimeStamp = struct.unpack('<I', bytes(payload[20:24]))

	print("Classification Type: %s" % decode_system_classification_type(classification_type))
	print("Operator Location Type: %s" % decode_system_operator_location_type(operator_location_type))
	print("Operator Latitude: %2.7f" % (float(OperatorLatitude)/(10*1000*1000)))
	print("Operator Longitude: %2.7f" % (float(OperatorLongitude)/(10*1000*1000)))
	print("Area Count: %i" % AreaCount)
	print("Area Radius: %i" % AreaRadius)
	print("Area Ceiling: %i" % ((int(AreaCeiling[0]) - int(2000))/2))
	print("Area Floor: %i" % ((int(AreaFloor[0]) - int(2000))/2))
	print("UA category: %s" % decode_system_ua_category(UA_category))
	print("UA class: %s" % decode_system_ua_class(UA_class))
	print("Operator Altitude: %2.1f" % ((int(OperatordAltitude[0]) - int(2000))/2))
	print("Timestamp: %s" % decode_system_timestamp(TimeStamp))

def print_operatorID(payload):
	operatorID_type = payload[1]
	operatorID = payload[2:2 + ODID_ID_SIZE]

	print("Type: %s" % decode_operatorID_type(operatorID_type))
	print("Text: %s" % clean_string(bytes(operatorID).decode('ascii')))

#removes characters like \t \n \r space from string
def clean_SN(string):
    string = string.replace(" ", "")
    string = string.replace("\t", "")
    string = string.replace("\n", "")
    string = string.replace("\r", "")

    return string

#removes characters like \t \n \r from string
def clean_string(string):
    string = string.replace("\t", "")
    string = string.replace("\n", "")
    string = string.replace("\r", "")

    return string

def decode_basicID_ID_type(IDType):
    string = ""
    if IDType == 0:
        string = "None"
    elif IDType == 1:
        string = "Serial Number"
    elif IDType == 2:
        string = "CAA Registration ID"
    elif IDType == 3:
        string = "UTM Assigned UUID"
    elif IDType == 4:
        string = "specific session ID"

    return string

def decode_basicID_UA_type(UAType):
    string = ""
    if UAType == 0:
        string = "None"
    elif UAType == 1:
        string = "Aeroplane"
    elif UAType == 2:
        string = "Helicopter (or Multirotor)"
    elif UAType == 3:
        string = "Gyroplane"
    elif UAType == 4:
        string = "Hybrid Lift"
    elif UAType == 5:
        string = "Ornithopter"
    elif UAType == 6:
        string = "Glider"
    elif UAType == 7:
        string = "Kite"
    elif UAType == 8:
        string = "Free Balloon"
    elif UAType == 9:
        string = "Captive Balloon"
    elif UAType == 10:
        string = "Airship (such as a blimp)"
    elif UAType == 11:
        string = "Free Fall/Parachute (unpowered)"
    elif UAType == 12:
        string = "Rocket"
    elif UAType == 13:
        string = "Tethered Powered Aircraft"
    elif UAType == 14:
        string = "Ground Obstacle"
    elif UAType == 15:
        string = "Other"

    return string

def decode_location_status(status):
    string = ""
    if status == 0:
        string = "Undeclared"
    elif status == 1:
        string = "Ground"
    elif status == 2:
        string = "Airborne"
    elif status == 3:
        string = "Emergency"
    elif status == 4:
        string = "Remote ID System Failure"

    return string

def decode_location_timestamp(timestamp):
    string = ""
    timestamp = int(timestamp[0])
    minutes = int(timestamp/10/60)
    seconds = int((timestamp - minutes*60*10)/10)
    seconds_decimals = int((timestamp - minutes*60*10)/10 - seconds)
    string = str(f"{minutes:02}") + ":" + str(f"{seconds:02}") + "." + str(f"{seconds_decimals:02}")

    return string

def decode_location_height_type(height_type):
    string = ""
    if height_type == 0:
        string = "Above Takeoff"
    elif height_type == 1:
        string = "Above Ground Level"

    return string

def decode_selfID_type(selfID_type):
    string = ""
    if selfID_type == 0:
        string = "Text"
    elif selfID_type == 1:
        string = "Emergency"
    elif selfID_type == 2:
        string = "Extended Status"

    return string

def decode_system_classification_type(system_classification_type):
    string = ""
    if system_classification_type == 0:
        string = "Undeclared"
    elif system_classification_type == 1:
        string = "European Union"

    return string

def decode_system_operator_location_type(operator_location_type):
    string = ""
    if operator_location_type == 0:
        string = "Take Off"
    elif operator_location_type == 1:
        string = "Dynamic"
    elif operator_location_type == 2:
        string = "Fixed"

    return string

def decode_system_ua_category(ua_category):
    string = ""
    if ua_category == 0:
        string = "Undefined"
    elif ua_category == 1:
        string = "Open"
    elif ua_category == 2:
        string = "Specific"
    elif ua_category == 3:
        string = "Certified"

    return string

def decode_system_ua_class(ua_class):
    string = ""
    if ua_class == 0:
        string = "Undefined"
    elif ua_class == 1:
        string = "Class 0"
    elif ua_class == 2:
        string = "Class 1"
    elif ua_class == 3:
        string = "Class 2"
    elif ua_class == 4:
        string = "Class 3"
    elif ua_class == 5:
        string = "Class 4"
    elif ua_class == 6:
        string = "Class 5"
    elif ua_class == 7:
        string = "Class 6"

    return string

def decode_system_timestamp(timestamp):
    string = ""
    timestamp = int(timestamp[0]) + 1546300800 # add 01/01/2019
    string = datetime.datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S') + " UTC"

    return string

def location_decode_speed_horizontal(speed_enc, speed_mult):
    if speed_enc == 255:
	    return float('NaN')
    speed_enc = float (speed_enc)
    if speed_mult == 1:
        return float ((float(speed_enc) * 0.75) + (255 * 0.25))
    else:
        return speed_enc * 0.75

def decode_operatorID_type(operatorID_type):
    string = ""
    if operatorID_type == 0:
        string = "Operator ID"

    return string

