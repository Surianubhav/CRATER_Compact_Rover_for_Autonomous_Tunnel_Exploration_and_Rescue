# CRATER — Compact Rover for Autonomous Tunnel Exploration & Rescue

<p align="center">
  <strong>An intelligent robotic platform for underground exploration, environmental monitoring, and search-and-rescue support.</strong>
</p>

<p align="center">
  <a href="https://youtu.be/ypSJ9OmCvYg?si=MKHVfJJ0d8UbY9vU">
    <img src="https://img.shields.io/badge/▶_Watch_Project_Demo-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="Watch CRATER Demo">
  </a>
  <img src="https://img.shields.io/badge/Smart_India_Hackathon-2026-blue?style=for-the-badge" alt="Smart India Hackathon 2026">
  <img src="https://img.shields.io/badge/Domain-Robotics_%7C_AI_%7C_Embedded_Systems-7C3AED?style=for-the-badge" alt="Project Domain">
</p>

---

## 🚀 The Project

Underground mines present some of the most challenging environments for exploration and emergency response. Toxic gas accumulation, unstable tunnels, poor visibility, structural damage, and unreliable communication can put both miners and rescue personnel at risk.

**CRATER (Compact Rover for Autonomous Tunnel Exploration & Rescue)** is a compact, tracked robotic platform designed to explore hazardous underground environments and provide operators with actionable information before human responders enter potentially dangerous areas.

Developed by **Team Treadmill** for Smart India Hackathon 2026, CRATER combines mobile robotics, LiDAR-based mapping, environmental sensing, computer vision, embedded motor control, and wireless networking into a modular exploration and rescue-support system.

The platform is designed to collect and communicate information about its surroundings, help operators understand unfamiliar tunnel layouts, and extend wireless connectivity using deployable relay nodes.

Rather than sending people into an unknown environment first, CRATER aims to send a robot.

## 📸 Meet CRATER

<p align="center">
  <img src="images/rover.jpg" alt="CRATER physical rover prototype" width="85%">
</p>

<p align="center">
  <em>The CRATER physical prototype — a compact, tracked rover developed for underground exploration and rescue support.</em>
</p>

### Key objectives

- **Explore hazardous environments:** Use a compact tracked chassis to traverse confined and uneven terrain.
- **Map unknown surroundings:** Capture LiDAR measurements and reconstruct tunnel geometry.
- **Monitor environmental conditions:** Collect sensor readings to help identify potentially hazardous environments.
- **Improve situational awareness:** Present maps, sensor telemetry, and camera feeds through an operator dashboard.
- **Extend communication:** Investigate and implement relay-based networking for environments where direct wireless connectivity is unreliable.
- **Support rescue decisions:** Provide remote observations that can help teams assess the environment before entering.

> **Project status:** CRATER is a physical robotics prototype with an evolving software and hardware stack. Individual capabilities may have different implementation and validation levels. This repository documents the system and its development without implying that every proposed feature has been fully validated in an operational mine.

---

## 📑 Table of Contents

- [How CRATER Works](#-how-crater-works)
- [System Architecture](#-system-architecture)
- [Mesh Networking](#-mesh-networking-and-relay-deployment)
- [Wi-Fi HaLow](#-wi-fi-halow-for-underground-connectivity)
- [Autonomy and Navigation](#-autonomy-and-navigation)
- [LiDAR Mapping and Point Clouds](#-lidar-mapping-and-point-cloud-reconstruction)
- [Environmental Monitoring](#-environmental-monitoring)
- [Computer Vision and Perception](#-computer-vision-and-perception)
- [Live Operator Dashboard](#-live-operator-dashboard)
- [Hardware Architecture](#-hardware-architecture)
- [Software Stack](#-software-stack)
- [Repository Structure](#-repository-structure)
- [Getting Started](#-getting-started)
- [Demonstrations](#-demonstrations)
- [Limitations and Future Work](#-limitations-and-future-work)
- [Team Treadmill](#-team-treadmill)
- [Acknowledgements](#-acknowledgements)

---

## ⚙️ How CRATER Works

CRATER is designed as a distributed robotic system rather than a single monolithic device. The rover, onboard compute, embedded controller, communication network, and operator interface have distinct responsibilities.

The system can be understood as five interconnected stages.

### 1. Sense the environment

The rover collects information using its onboard sensing hardware.

Depending on the active configuration, this includes:

- LiDAR distance measurements for spatial reconstruction.
- RGB imagery for visual observation.
- Environmental measurements such as gas concentration, temperature, and humidity.
- Inertial measurements for estimating orientation and motion.
- Wheel encoder measurements for tracking drivetrain movement.

### 2. Process sensor data

The onboard computing system processes the incoming data. The intended processing pipeline combines spatial reconstruction, perception, telemetry handling, and navigation logic.

Computationally intensive perception tasks are separated from low-level hardware control, allowing the system to evolve without tightly coupling every subsystem.

### 3. Move and estimate motion

The embedded controller operates the left and right drive systems. Encoder feedback and inertial measurements can be used to estimate rover displacement and orientation.

These estimates provide the foundation for mapping, motion tracking, and autonomous navigation.

### 4. Communicate underground

The communication subsystem carries relevant observations and telemetry toward the operator. Relay nodes are intended to extend the network when the rover moves beyond the useful range of a direct link.

### 5. Visualize mission information

The operator dashboard provides a unified interface for observing the rover, inspecting map outputs, reviewing sensor information, and issuing supported commands.

The goal is to turn raw measurements into an understandable representation of the environment.

---

## 🧠 System Architecture

CRATER integrates onboard perception, embedded hardware control, wireless communication, and a remote operator interface into a modular robotic platform.

The system architecture and data flow are illustrated in the following diagrams.

<p align="center">
  <img src="images/system_architecture.png" alt="CRATER system architecture flowchart" width="100%">
</p>

*System architecture showing the interaction between the rover's sensing, processing, control, and communication subsystems.*

<p align="center">
  <img src="images/technical_flowchart.png" alt="CRATER technical workflow" width="100%">
</p>

*Technical workflow illustrating sensor data processing, rover control, telemetry transmission, and operator interaction.*

## 📡 Mesh Networking and Relay Deployment

Communication is one of the central challenges in underground robotics.

Unlike open environments, mines and tunnels contain bends, intersections, confined passages, and rock formations that can significantly attenuate or block radio signals. A rover may therefore lose its direct connection to the operator as it explores deeper into the environment.

CRATER explores a relay-based networking architecture to address this limitation.

<p align="center">
  <img src="images/mesh_network.png" alt="CRATER mesh network" width="90%">
</p>

<em>Replace with the mesh-network topology or a photograph showing the relay nodes.</em>

### How the network is intended to work

1. **Rover node:** The rover collects measurements and produces mission telemetry.
2. **Relay nodes:** Wireless relay devices are positioned along the exploration route.
3. **Multi-hop communication:** Data can travel through intermediate nodes when supported by the networking implementation.
4. **Surface gateway:** A node connected to the operator station forwards available telemetry to the dashboard.
5. **Operator feedback:** Commands and mission updates travel back toward the rover when a return path is available.

### Why relay-based networking matters

- Reduces dependence on a single direct radio link.
- Can extend useful communication coverage through a sequence of network nodes.
- Supports distributed sensing and remote monitoring.
- Can provide alternate communication paths if the network supports route recovery.
- Reduces the need to run long physical communication cables through the tunnel.

### Autonomous relay deployment

CRATER's design includes the concept of a rover that carries and deploys wireless relay nodes during exploration.

This is intended to create a communication path progressively as the rover moves farther into a tunnel.

The relay deployment mechanism, node placement strategy, and automatic recovery behavior should be documented according to the implementation demonstrated by the physical prototype.

**Important distinction:** A network should only be described as self-healing if it has been tested to recover connectivity or reroute traffic following a node or link failure. Similarly, autonomous deployment should be identified as implemented only when the rover can perform the deployment without manual placement.

---

## 📶 Wi-Fi HaLow for Underground Connectivity

Wi-Fi HaLow, based on IEEE 802.11ah, is a sub-GHz Wi-Fi technology designed for applications that benefit from lower-frequency wireless communication and extended range.

CRATER's communication design considers Wi-Fi HaLow as a potential or configured transport for underground telemetry and relay connectivity.

### Why consider Wi-Fi HaLow?

- **Sub-GHz operation:** Lower-frequency propagation can offer useful range and penetration advantages in some environments compared with conventional 2.4 GHz Wi-Fi.
- **IP networking:** Compatible implementations can support IP-based data transport and familiar network tooling.
- **Telemetry transmission:** Sensor readings, status updates, and control messages are natural candidates for wireless transport.
- **Distributed infrastructure:** Multiple supported network nodes can help extend connectivity beyond a single radio link.

### Practical considerations

Wi-Fi HaLow does not guarantee communication through solid rock or every tunnel configuration. Actual performance depends on the radio hardware, antenna placement, rock composition, tunnel geometry, interference, and regulatory constraints.

The system should be evaluated using measurements such as:

- Link availability and packet delivery ratio.
- End-to-end telemetry latency.
- Throughput under representative workloads.
- Communication performance around tunnel bends.
- Recovery time after a relay becomes unavailable.
- Maximum tested range under documented conditions.

If Wi-Fi HaLow hardware is not yet integrated into the physical prototype, describe it as a planned communication subsystem rather than an operational capability.

---

## 🤖 Autonomy and Navigation

Autonomous underground exploration requires the rover to reason about movement without relying on GPS or a previously constructed map.

CRATER's navigation architecture uses motion feedback and spatial sensing as the foundation for progressively more capable autonomous behavior.

<p align="center">
  <img src="images/autonomy_flowchart.png" alt="CRATER autonomy and navigation flowchart" width="100%">
</p>

### Motion estimation

The tracked drive system uses left and right motor actuation to move the rover. Wheel encoder feedback can estimate wheel rotation, while an inertial measurement unit (IMU) provides information about angular motion and orientation.

These signals can be combined to estimate the rover's movement.

For differential-drive-style odometry, let:

- \(\Delta s_L\) be the left track's estimated displacement.
- \(\Delta s_R\) be the right track's estimated displacement.
- \(b\) be the effective distance between the left and right track contact paths.

The approximate change in forward displacement is:

\[
\Delta s = \frac{\Delta s_R+\Delta s_L}{2}
\]

The approximate change in heading is:

\[
\Delta\theta = \frac{\Delta s_R-\Delta s_L}{b}
\]

These equations provide a starting point for estimating motion. Track slip, uneven terrain, mechanical tolerances, and encoder errors can cause drift.

### Navigation pipeline

The intended navigation pipeline can be organized into the following stages:

1. Read motion and distance measurements.
2. Estimate rover displacement and heading.
3. Process LiDAR observations to understand nearby geometry.
4. Update the local representation of the environment.
5. Evaluate candidate movements against obstacles and mission objectives.
6. Send motion commands to the embedded controller.
7. Repeat the process as new measurements arrive.

### Levels of autonomy

| Capability | Purpose |
|---|---|
| Remote operation | Allows an operator to control rover movement. |
| Motion feedback | Estimates displacement and orientation from onboard sensors. |
| Local obstacle awareness | Uses spatial measurements to identify nearby obstacles. |
| Map-assisted navigation | Uses a reconstructed environment to support route decisions. |
| Autonomous exploration | Selects and executes exploration actions with limited operator input. |
| Return-to-base behavior | Attempts to return along a known route when appropriate. |

These capabilities represent different levels of system sophistication. Only the levels implemented and validated in the current codebase should be marked as operational.

---

## 🗺️ LiDAR Mapping and Point-Cloud Reconstruction

Understanding the geometry of an unfamiliar tunnel is essential for exploration and rescue planning.

CRATER uses LiDAR measurements to reconstruct the surrounding environment. The mapping pipeline processes distance observations into spatial representations that can help operators understand tunnel structure and rover movement.

<p align="center">
  <img src="images/point_cloud.png" alt="Actual CRATER LiDAR point cloud" width="95%">
</p>

<p align="center">
  <img src="images/lidar_map.png" alt="Actual CRATER LiDAR map" width="95%">
</p>

### 3D point-cloud visualization

<p align="center">
  <img src="images/point_cloud.png" alt="CRATER LiDAR point-cloud reconstruction" width="95%">
</p>

<em>Replace with an actual point-cloud screenshot showing the geometry captured by the rover's LiDAR.</em>

A point cloud represents observed surfaces as a collection of spatial points. Depending on the sensor and processing pipeline, it can reveal:

- Tunnel walls and passage geometry.
- Changes in corridor width and direction.
- Nearby obstructions and structural features.
- Relative spatial relationships between observed surfaces.
- Geometry that can support later mapping and navigation stages.

### LiDAR map

<p align="center">
  <img src="images/lidar_map.png" alt="CRATER generated LiDAR map" width="95%">
</p>

<em>Replace with the actual map generated by your mapping software.</em>

The map provides a more compact representation of the explored environment. It can help an operator interpret the rover's surroundings without relying exclusively on live camera footage.

### Sensor fusion

LiDAR alone provides distance observations, but mapping a moving rover also requires estimating how the sensor changes position over time.

CRATER's motion-estimation approach uses:

- **LiDAR:** Observations of surrounding surfaces.
- **Wheel encoders:** Estimates of track movement and displacement.
- **IMU:** Angular motion and orientation measurements.

Combining these measurements can improve motion estimation compared with relying on any one source alone. However, sensor fusion does not automatically eliminate drift; calibration and validation remain essential.

### Mapping development goals

- Improve odometry calibration.
- Reduce accumulated pose drift.
- Handle track slippage and uneven surfaces.
- Improve point-cloud alignment.
- Build more consistent maps over longer exploration runs.
- Integrate map outputs with obstacle-aware navigation.

The repository should document the exact LiDAR model, sampling rate, mapping algorithm, coordinate frames, and output format used by the working implementation.

---

## 🌡️ Environmental Monitoring

A rescue-support rover must provide more than a visual representation of its surroundings. Environmental information can help operators identify conditions that warrant further investigation.

CRATER's proposed sensing architecture includes environmental measurements alongside spatial and visual observations.

### Sensor categories

| Sensor category | Intended purpose |
|---|---|
| Gas sensing | Monitor selected gases relevant to the intended deployment. |
| Temperature | Measure local ambient temperature. |
| Humidity | Monitor ambient humidity. |
| IMU | Measure inertial motion and orientation. |
| Wheel encoders | Estimate drivetrain movement. |
| LiDAR | Measure surrounding distances and reconstruct geometry. |
| RGB camera | Provide visible-light imagery. |
| Thermal camera | Provide thermal imagery when compatible hardware is installed. |

### Hazard monitoring pipeline

1. Acquire readings from the available sensors.
2. Associate measurements with timestamps.
3. Apply appropriate calibration and basic validation.
4. Transmit readings to the operator interface when connectivity is available.
5. Display readings and flag configured thresholds.
6. Preserve relevant observations for later analysis, if logging is implemented.

Sensor readings should be interpreted with appropriate calibration, environmental compensation, and sensor-specific limitations.

**Safety note:** CRATER is a research and prototype platform, not a certified mine-safety instrument or intrinsically safe underground vehicle. Its measurements must not be used as the sole basis for declaring an environment safe for human entry.

---

## 👁️ Computer Vision and Perception

Visual sensing can complement LiDAR by providing information about objects and environmental features that may not be immediately apparent from geometry alone.

CRATER's architecture considers RGB and thermal perception as complementary sources of information.

### RGB vision

Visible-light imagery can help with:

- Remote visual inspection.
- Identifying objects in illuminated environments.
- Observing terrain and obstacles.
- Providing operators with additional context alongside the map.

### Thermal perception

Thermal imaging can help reveal temperature patterns when conventional visual observation is limited by poor illumination.

Potential applications include identifying warm objects and investigating possible human presence. Thermal anomalies alone do not confirm that an object is a person or a survivor.

## 🖥️ Live Operator Dashboard

The dashboard is the primary interface between the rover and its operator.

It is designed to consolidate information from multiple subsystems into one interface, reducing the need to inspect separate tools during an exploration run.

<p align="center">
  <img src="images/dashboard.png" alt="CRATER live operator dashboard" width="95%">
</p>

<em>Replace with a screenshot of the actual CRATER dashboard.</em>

### Dashboard components

The interface can bring together the following views, depending on which subsystems are connected:

- **Live rover status:** Connection state and available system telemetry.
- **Mapping view:** LiDAR-derived spatial information and map outputs.
- **Camera feed:** Live or recorded visual observations.
- **Environmental telemetry:** Available gas, temperature, and humidity measurements.
- **Motion information:** Odometry or movement information when exposed by the control system.
- **Connectivity status:** Information about the rover-to-operator communication link.
- **Alerts:** Configured warnings for sensor thresholds or system events.
- **Control interface:** Supported commands for operating the rover.

### Why a unified dashboard matters

In an unfamiliar underground environment, an operator must understand not only what the rover sees, but also where it is, what environmental conditions it measures, and whether communication is reliable.

The dashboard aims to combine these information sources into a coherent operational view.

---

## 🔩 Hardware Architecture

CRATER combines a tracked mechanical platform with sensing, computation, embedded control, and wireless communication hardware.

### Mechanical platform

<p align="center">
  <img src="images/rover_chassis.jpg" alt="CRATER tracked mechanical chassis" width="80%">
</p>

The compact tracked chassis is designed to support movement across uneven surfaces while maintaining a relatively small footprint.

The mechanical design can be extended with sensor mounts, electronics enclosures, and relay-carrying mechanisms as the platform evolves.

### Hardware subsystem overview

| Subsystem | Responsibility |
|---|---|
| Tracked drivetrain | Provides rover movement and turning. |
| Onboard computer | Runs supported high-level processing and mission software. |
| Microcontroller | Handles low-level motor control and connected sensors. |
| LiDAR | Collects spatial measurements. |
| RGB camera | Provides visible-light observations. |
| Thermal camera | Provides thermal imagery when installed. |
| Environmental sensors | Collect configured environmental measurements. |
| IMU | Provides inertial measurements. |
| Wheel encoders | Provide motion feedback. |
| Wireless interface | Provides the configured communication link. |
| Relay hardware | Extends communication where the deployment supports it. |
| Power system | Supplies power to the rover's electronics and drive system. |

### Hardware documentation

The exact bill of materials, wiring diagrams, connector assignments, power requirements, and part numbers should be maintained alongside the relevant subsystem documentation.

This makes the project easier to reproduce, debug, and extend.

---

## 💻 Software Stack

CRATER's software is organized around the responsibilities of each subsystem.

The final stack should reflect the actual libraries, frameworks, firmware, and tools present in the repository.

| Software layer | Role |
|---|---|
| Embedded firmware | Motor actuation, sensor acquisition, and low-level control. |
| Onboard application | Coordinates supported high-level processing and mission logic. |
| Mapping software | Processes spatial measurements into map representations. |
| Perception software | Processes visual data where AI perception is implemented. |
| Communication software | Transports supported telemetry and control messages. |
| Dashboard application | Visualizes available rover information and exposes supported controls. |
| Data processing tools | Support calibration, analysis, visualization, and testing. |

### Development principles

- Keep hardware control separate from high-level perception.
- Document sensor interfaces and message formats.
- Make calibration parameters explicit.
- Separate experimental algorithms from validated functionality.
- Provide repeatable test procedures.
- Record known limitations and expected behavior.

---
## 🛠️ Getting Started

Because CRATER integrates physical hardware and multiple software subsystems, the setup process depends on the particular module being used.

### Prerequisites

Depending on the component you want to run, you may need:

- Git.
- Python and the dependencies required by the mapping or perception software.
- The relevant embedded development environment.
- Drivers and interfaces required by the connected sensors.
- The appropriate onboard computing hardware.
- Access to the rover's communication interface.
- The dashboard's required runtime and dependencies.

### 1. Clone the repository

```bash
git clone https://github.com/Surianubhav/CRATER_Compact_Rover_for_Autonomous_Tunnel_Exploration_and_Rescue.git

cd CRATER_Compact_Rover_for_Autonomous_Tunnel_Exploration_and_Rescue
```

### 2. Inspect the project

```bash
ls -la
```

Review the available source directories and the instructions for the subsystem you intend to run.

### 3. Install subsystem dependencies

Install the dependencies documented by the relevant module.

For a Python-based component, if a `requirements.txt` is provided:

```bash
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

Run this from the directory containing the relevant dependency file. If the repository uses another dependency manager, follow its documented setup instead.

### 4. Configure the hardware

Before powering the rover:

- Verify power supply voltages and current requirements.
- Check motor-driver connections and polarity.
- Verify sensor interfaces and communication settings.
- Calibrate the encoders and IMU as required.
- Confirm that the communication link is configured correctly.
- Ensure that the wheels or tracks are safely supported during initial motor tests.

### 5. Run the selected subsystem

Follow the subsystem-specific instructions for firmware, mapping, perception, or the dashboard.

The exact launch commands should be added after confirming the current entry points and configuration files in the repository.

### 6. Validate the system

Begin with stationary sensor checks, then test drivetrain movement, mapping, telemetry, and operator-interface integration independently before attempting an integrated exploration run.

**Note:** The commands above cover repository setup and a generic Python environment. They are not a complete hardware bring-up procedure; module-specific launch instructions and configuration values must be documented separately.

---


## 🚧 Limitations and Future Work

CRATER is an evolving robotics platform. Its development roadmap focuses on improving the reliability, integration, and practical utility of its subsystems.

### 1. More reliable localization

Improve the consistency of odometry and mapping by refining encoder calibration, inertial measurements, and motion estimation under track slip and uneven terrain.

### 2. Robust autonomous exploration

Develop and validate obstacle-aware navigation, exploration planning, safe stopping, and recovery behavior for confined underground environments.

### 3. Communication resilience

Evaluate the actual performance of the selected wireless technology in representative tunnels, including attenuation, interference, packet loss, and relay failure.

### 4. Reliable relay deployment

Improve the mechanical deployment mechanism and develop strategies for positioning relay nodes to maintain useful communication coverage.

### 5. Integrated perception

Where compatible hardware and trained models are available, integrate visual and thermal perception with spatial information to help operators investigate objects and possible hazards.

### 6. Improved environmental monitoring

Calibrate the environmental sensors, validate their readings, implement suitable alert thresholds, and characterize the limits of each sensing module.

### 7. Better operator situational awareness

Improve the synchronization and presentation of maps, telemetry, camera feeds, and connectivity status.

### 8. Repeatable testing

Develop documented test procedures for mapping accuracy, localization drift, obstacle traversal, communication reliability, sensor performance, and mission recovery.

### 9. Safety and deployment readiness

Evaluate enclosure protection, electrical safety, fault handling, and the requirements for operation in potentially explosive atmospheres. Deployment in an operational mine would require appropriate engineering validation and applicable safety certification.

---

## 👥 Team Treadmill

CRATER was developed by **Team Treadmill** for Smart India Hackathon 2026.

**Problem Statement:** 26039 — AI-Powered Underground Mine Safety, Monitoring and Rescue System

**Theme:** Smart Automation

**Category:** Hardware

<p align="center">
  <img src="images/team.jpg" alt="Team Treadmill — CRATER project team" width="85%">
</p>

<p align="center">
  <em>The people behind CRATER.</em>
</p>

### Contributors

Add each team member's name, project responsibilities, and relevant links below.

| Team member | Contribution | Profile |
|---|---|---|
| [Member 1] | [Role and contributions] | [GitHub / LinkedIn] |
| [Member 2] | [Role and contributions] | [GitHub / LinkedIn] |
| [Member 3] | [Role and contributions] | [GitHub / LinkedIn] |
| [Member 4] | [Role and contributions] | [GitHub / LinkedIn] |
| [Member 5] | [Role and contributions] | [GitHub / LinkedIn] |

Update the table to include the actual team members and their respective contributions.

---
