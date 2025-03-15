# HomeAssistant-BMR

Home Assistant integration plugin for [BMR HC64 heating
controller](https://bmr.cz/produkty/regulace-topeni/rnet). This controller has
many quirks but overall it is quite usable in Home Assistant.  The plugin
provides entities from these Home Assistant platforms:

- `binary_sensor`
- `climate`
- `sensor`
- `switch`


## Installation

For normal use, use HACS to install the plugin. I assume you already have HACS
in your Home Assistnt installation.

Steps:

1. Open "Community Store" in the side menu

2. Click the "dots" menu in the top-right corner

3. Select "Custom repositories"

4. Enter `https://github.com/dankeder/HomeAssistant-BMR` into "Repository" field and choose "Integration" in the "Type" field

5. Click "Add" and close the dialog

6. A new integration "BMR HC64" should now be available for download. Find it and click the "Download" button.


Alternatively you can install the plugin manually: copy `custom_components/` to
your Home Assistant `config` directory.


## Configuration

The integration is configured using the Home Assistant UI. The YAML configuration is no longer supported.

Add the BMR HC64 controller device to Home Assistant:

1. Go to "Settings -> Devices & Services"

2. Click "Add integration" in the bottom right corner

3. Search for "BMR HC64", then click on it to show the configuration dialog

4. Fill in the form

5. Click Submit.


Add heating circuits:

1. Go to "Settings -> Devices & Services -> BMR HC64"

2. Click the three dots to show the BMR HC64 controller menu

3. In the menu click "Add heating circuit"

4. Fill-in the form

5. Click Submit

6. Repeat for every circuit you want to configure.


## Provided entities

The actual names of entities depend on the controller device name that was configured above.

### Binary Sensor

Provided entities:

- `binary_sensor.<controller-name>_hdo`: Binary sensor for indicating the state of HDO (low/high electricity tariff)


### Climate

Climate entity for the given heating circuit. It supports setting HVAC mode,
HVAC presets, target temperature, power on/off.

Provided entities:

-  `climate.<controller-name>_<circuit-name>` for every configured circuit

The concept of "circuits" represents heating circuits that will be handled by
the integration. Usually the circuit corresponds to a room it is located in,
but sometimes the circuit can heat multiple rooms as well.

In my heating system the HC64 controller has two circuits per room - the "room"
circuit which is measuring air temperature and "floor" circuit which is
measuring floor temperature. Controller will start heating when both circuits
have lower temperature than their target temperature. An electrician would say
they are conected in series. This is unneccesarily complicated and it sometimes
results in unpredictable behaviour so I recommended to configure the floor
circuit in such a way that it almost always "wants" to heat by setting its
target temperature to a high value (e.g. 32 C) and configure only the "room"
circuit in Home Assistant.

Supported HVAC modes:

- Auto mode: Let the heating controller manage the temperature automatically
using the configured schedules. It is possible to configure up to 21 schedules
that are rotated daily.

- Heating (Manual mode): Set the target temperature for the circuit manually.
This works by switching the circuit to a "manual" schedule specified in circuit
configuration and setting the target temperature of the schedule. Make sure the
"manual" schedule is not used by some other circuit, otherwise you will observe
weird behaviour. The reason for using a special schedule for manual mode
is to preserve settings of the schedules used by Auto mode.

- Off: Turn off the heating circuit. Internally this works by assigning the
circuit into the "summer mode" and turning the summer mode on.

Supported HVAC presets:

- None: Normal operation, the controller will control target temperature
according to the configured schedules

- Away: Turn on the "away" mode. This will set the target temperature of the
circuit to the configured "Away temperature". Intenally this works by turning
on the "low" mode of the HC64 controller and assigning the affected circuits to
it.


### Sensor

Sensor entities for reporting current and target temperature of circuits.

Provided entities:

- `sensor.<controller-name_<circuit-name>_temperature` for every configured circuit
- `sensor.<controller-name_<circuit-name>_target_temperature` for every configured circuit


### Switch

Switches for controlling the "Away" mode and "Power". When these are used they
affect all configured circuits.

Provided entities:

- `switch.<controller-name>_away`
- `switch.<controller-name>_power`

The `switch.bmr_hc64_away` switch will toggle the "Away" mode for all
configured circuits. Internally this works by turning on the "low" mode in the
controller and assigning all circuits to it.

The `switch.bmr_hc64_power` switch will toggle power for all circuits.
Internally this works by enabling the "summer" mode in the controller and and
assigning all circuits to it.


## Cooling support

Cooling support is implemented, but it has not been tested (I don't have a
water-based circuits). But it should work. Probably.


[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
