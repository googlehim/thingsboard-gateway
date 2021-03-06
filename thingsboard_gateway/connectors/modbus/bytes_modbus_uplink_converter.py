#     Copyright 2020. ThingsBoard
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.

from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.exceptions import ModbusIOException

from thingsboard_gateway.connectors.modbus.modbus_converter import ModbusConverter, log


class BytesModbusUplinkConverter(ModbusConverter):
    def __init__(self, config):
        self.__datatypes = {
            "timeseries": "telemetry",
            "attributes": "attributes"
        }
        self.__result = {"deviceName": config.get("deviceName", "ModbusDevice %s" % (str(config["unitId"]))),
                         "deviceType": config.get("deviceType", "default")}

    def convert(self, config, data):
        self.__result["telemetry"] = []
        self.__result["attributes"] = []
        for config_data in data:
            for tag in data[config_data]:
                configuration = data[config_data][tag]["data_sent"]
                response = data[config_data][tag]["input_data"]
                byte_order = configuration.get("byteOrder", "LITTLE")
                endian_order = Endian.Little if byte_order.upper() == "LITTLE" else Endian.Big
                decoded_data = None
                if not isinstance(response, ModbusIOException):
                    if configuration["functionCode"] in [1, 2]:
                        result = response.bits
                        result = result if byte_order.upper() == 'LITTLE' else result[::-1]
                        log.debug(result)
                        if "bit" in configuration:
                            decoded_data = result[configuration["bit"]]
                        else:
                            decoded_data = result[0]
                    elif configuration["functionCode"] in [3, 4]:
                        decoder = None
                        registers = response.registers
                        log.debug("Tag: %s Config: %s registers: %s", tag, str(configuration), str(registers))
                        try:
                            decoder = BinaryPayloadDecoder.fromRegisters(registers, byteorder=endian_order)
                        except TypeError:
                            # pylint: disable=E1123
                            decoder = BinaryPayloadDecoder.fromRegisters(registers, endian=endian_order)
                        assert decoder is not None
                        decoded_data = self.__decode_from_registers(decoder, configuration)
                        if configuration.get("divider"):
                            decoded_data = float(decoded_data) / float(configuration["divider"])
                        if configuration.get("multiplier"):
                            decoded_data = decoded_data * configuration["multiplier"]
                else:
                    log.exception(response)
                    decoded_data = None
                if config_data == "rpc":
                    return decoded_data
                log.debug("datatype: %s \t key: %s \t value: %s", self.__datatypes[config_data], tag, str(decoded_data))
                self.__result[self.__datatypes[config_data]].append({tag: decoded_data})
        log.debug(self.__result)
        return self.__result

    @staticmethod
    def __decode_from_registers(decoder, configuration):
        type_ = configuration["type"]
        registers_count = configuration.get("registerCount", 1)
        lower_type = type_.lower()

        decoder_functions = {
            'string': decoder.decode_string,
            'bit': decoder.decode_bits,
            'bits': decoder.decode_bits,
            '8int': decoder.decode_8bit_int,
            '8uint': decoder.decode_8bit_uint,
            '16int': decoder.decode_16bit_int,
            '16uint': decoder.decode_16bit_uint,
            '16float': decoder.decode_16bit_float,
            '32int': decoder.decode_32bit_int,
            '32uint': decoder.decode_32bit_uint,
            '32float': decoder.decode_32bit_float,
            '64int': decoder.decode_64bit_int,
            '64uint': decoder.decode_64bit_uint,
            '64float': decoder.decode_64bit_float,
        }

        decoded = None
        if lower_type in ['int', 'long', 'integer']:
            type_ = str(registers_count * 16) + "int"
            assert decoder_functions.get(type_) is not None
            decoded = decoder_functions[type_]()

        elif lower_type in ["double", "float"]:
            type_ = str(registers_count * 16) + "float"
            assert decoder_functions.get(type_) is not None
            decoded = decoder_functions[type_]()

        elif lower_type == 'uint':
            type_ = str(registers_count * 16) + "uint"
            assert decoder_functions.get(type_) is not None
            decoded = decoder_functions[type_]()

        elif lower_type == "string":
            decoded = decoder_functions[type_](registers_count * 2)

        elif lower_type == 'bit':
            bit_address = configuration["bit"]
            decoded = decoder_functions[type_]()[bit_address]

        elif lower_type == 'bits':
            decoded = decoder_functions[type_]()

        elif decoder_functions.get(lower_type) is not None:
            decoded = decoder_functions[lower_type]()

        else:
            log.error("Unknown type: %s", type_)

        if isinstance(decoded, int):
            result_data = decoded
        elif isinstance(decoded, bytes):
            result_data = decoded.decode('UTF-8')
        elif isinstance(decoded, list):
            result_data = str(decoded)
        elif isinstance(decoded, float):
            result_data = decoded
        elif decoded is not None:
            result_data = int(decoded, 16)
        else:
            result_data = decoded

        return result_data
