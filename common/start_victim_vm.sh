#!/usr/bin/env bash
set -euo pipefail

# start_victim_vm.sh - Start victim VM for network labs
#
# Usage:
#   ./start_victim_vm.sh                       # Start victim VM
#   USE_SNAPSHOT=yes ./start_victim_vm.sh      # Boot from snapshot
#   VICTIM_NUM=1 ./start_victim_vm.sh          # Multiple victims

PATH=/run/dojo/bin/:$PATH

# Configuration
VICTIM_NUM="${VICTIM_NUM:-1}"
BASE_IMG="${BASE_IMG:-/vms/ubuntu-24.04-victim.qcow2}"
WORKDIR="${WORKDIR:-/tmp/vm-victim${VICTIM_NUM}}"
MEM="${MEM:-1024}"
CPUS="${CPUS:-2}"
USE_SNAPSHOT="${USE_SNAPSHOT:-no}"
SNAPSHOT_NAME="${SNAPSHOT_NAME:-ready}"
NETWORK_MODE="${NETWORK_MODE:-dual}"  # "dual" (SSH+L2), "socket" (L2 only)

# Network settings - different ports and MACs per victim
SSH_PORT="${SSH_PORT:-$((2222 + VICTIM_NUM))}"
MAC_ADDR="${MAC_ADDR:-52:54:00:12:34:$(printf '%02x' $((VICTIM_NUM + 10)))}"
MCAST_ADDR="${MCAST_ADDR:-230.0.0.1:1234}"

ATTENDANCE_SENTINEL="/tmp/.attendance_check_before_victim_done"
if [ -f /challenge/bin/attendance_check.py ] && [ ! -f "$ATTENDANCE_SENTINEL" ]; then
  echo "[v] Running one-shot attendance check before victim VM startup"
  touch /var/log/attendance_check.log 2>/dev/null || true
  chmod 0644 /var/log/attendance_check.log 2>/dev/null || true
  set +e
  ATTENDANCE_CHECK_ONCE=1 python3 /challenge/bin/attendance_check.py
  attendance_status=$?
  set -e
  echo "[v] One-shot attendance check completed with exit code ${attendance_status}"
  touch "$ATTENDANCE_SENTINEL"
fi

# Sanity checks
if [ ! -f "${BASE_IMG}" ]; then
  echo "Error: Base image not found at ${BASE_IMG}" >&2
  exit 1
fi

mkdir -p "${WORKDIR}"
cd "${WORKDIR}"

# Determine boot image
SNAPSHOT_EXISTS=false
if [ "${USE_SNAPSHOT}" = "yes" ]; then
  if qemu-img snapshot -l "${BASE_IMG}" 2>/dev/null | grep -q "^[0-9]*.*${SNAPSHOT_NAME}"; then
    SNAPSHOT_EXISTS=true
    BOOT_IMG="${BASE_IMG}"
    echo "✓ Found snapshot '${SNAPSHOT_NAME}' - will boot instantly"
  else
    echo "Error: USE_SNAPSHOT=yes but snapshot '${SNAPSHOT_NAME}' not found in ${BASE_IMG}" >&2
    echo "Available snapshots:" >&2
    qemu-img snapshot -l "${BASE_IMG}" 2>&1 || echo "  (none)" >&2
    exit 1
  fi
else
  # Boot directly from base image for snapshot creation (no copy, no overlay)
  BOOT_IMG="${BASE_IMG}"
  echo "Booting base image directly for snapshot creation"
fi

printf "which qemu-system-x86_64: "
which qemu-system-x86_64
echo " "

# Build QEMU arguments
QEMU_ARGS=(
  -machine type=pc-i440fx-9.2
  -m "${MEM}"
  -smp "${CPUS}"
)

# Drive configuration with file locking based on snapshot usage
if [ "${USE_SNAPSHOT}" = "yes" ]; then
  # Snapshots are read-only, safe to disable locking for multiple VMs
  QEMU_ARGS+=(-drive "file=${BOOT_IMG},if=virtio,format=qcow2,file.locking=off")
  echo "Drive: ${BOOT_IMG} (locking disabled for snapshot mode)"
else
  # Normal boot with locking enabled for safety
  QEMU_ARGS+=(-drive "file=${BOOT_IMG},if=virtio,format=qcow2")
  echo "Drive: ${BOOT_IMG} (locking enabled)"
fi

QEMU_ARGS+=(-device virtio-serial)

# Network configuration
if [ "${NETWORK_MODE}" = "dual" ]; then
  # Dual NIC: user mode (SSH) + socket (L2)
  QEMU_ARGS+=(
    -device virtio-net-pci,netdev=net0
    -netdev user,id=net0,hostfwd=tcp::${SSH_PORT}-:22
    -device virtio-net-pci,netdev=net1,mac="${MAC_ADDR}"
    -netdev socket,id=net1,mcast="${MCAST_ADDR}"
  )
  echo "Network: SSH on port ${SSH_PORT} + L2 at ${MCAST_ADDR}"
elif [ "${NETWORK_MODE}" = "socket" ]; then
  # Socket only (serial console access)
  QEMU_ARGS+=(
    -device virtio-net-pci,netdev=net0,mac="${MAC_ADDR}"
    -netdev socket,id=net0,mcast="${MCAST_ADDR}"
  )
  echo "Network: L2 only at ${MCAST_ADDR} (serial console)"
else
  echo "Error: Invalid NETWORK_MODE=${NETWORK_MODE}" >&2
  exit 1
fi

# Add 9p device to match student VM's snapshot (mount to /challenge)
if [ -d "/challenge" ]; then
  SHARED_DIR="${SHARED_DIR:-/challenge}"
else
  SHARED_DIR="${SHARED_DIR:-/tmp/dummy-victim-data}"
  mkdir -p "${SHARED_DIR}" 2>/dev/null || true
fi
QEMU_ARGS+=(
  -fsdev local,id=fsdev0,path="${SHARED_DIR}",security_model=mapped
  -device virtio-9p-pci,fsdev=fsdev0,mount_tag=challenge
)
echo "9p share: ${SHARED_DIR} -> /challenge"

# Load snapshot if requested
if [ "${SNAPSHOT_EXISTS}" = true ]; then
  QEMU_ARGS+=( -loadvm "${SNAPSHOT_NAME}" )
fi

# Start VM
echo ""
echo "Starting victim VM #${VICTIM_NUM}..."
echo "  Image: ${BOOT_IMG}"
echo "  MAC: ${MAC_ADDR}"
echo ""

# Setup serial socket and monitor
SERIAL_SOCK="${WORKDIR}/serial.sock"
MONITOR_SOCK="${WORKDIR}/monitor.sock"
PID_FILE="${WORKDIR}/vm.pid"

# Remove old sockets if they exist
rm -f "${SERIAL_SOCK}" "${MONITOR_SOCK}"

# Add monitor socket to QEMU args
QEMU_ARGS+=(
  -serial unix:"${SERIAL_SOCK}",server,nowait
  -monitor unix:"${MONITOR_SOCK}",server,nowait
)

if [ "${USE_SNAPSHOT}" != "yes" ]; then
  # NOT using snapshot - daemon mode for manual network setup and savevm
  echo "Starting in daemon mode for snapshot creation"
  echo ""
  echo "To create snapshot:"
  echo "  1. Connect to serial: socat - UNIX-CONNECT:${SERIAL_SOCK}"
  echo "  2. Login as student/student"
  echo "  3. Manually configure network (bring up interfaces, get DHCP, etc)"
  echo "  4. Disconnect from serial (Ctrl+C)"
  echo "  5. Connect to monitor: socat - UNIX-CONNECT:${MONITOR_SOCK}"
  echo "  6. Type: savevm ${SNAPSHOT_NAME}"
  echo "  7. Type: quit"
  echo ""
  
  qemu-system-x86_64 "${QEMU_ARGS[@]}" \
    -display none \
    -daemonize \
    -pidfile "${PID_FILE}"
  
  echo ""
  echo "✅ Victim VM #${VICTIM_NUM} started for snapshot creation"
  echo "   Serial: socat -,raw,echo=0,escape=0x1d UNIX-CONNECT:${SERIAL_SOCK}  # Press Ctrl+] to disconnect"
  echo "   Monitor: socat - UNIX-CONNECT:${MONITOR_SOCK}"
  echo "   PID: $(cat ${PID_FILE} 2>/dev/null || echo 'unknown')"
  echo ""
else
  # Using snapshot - daemon mode with SSH
  qemu-system-x86_64 "${QEMU_ARGS[@]}" \
    -display none \
    -daemonize \
    -pidfile "${PID_FILE}"
  
  echo ""
  echo "✅ Victim VM #${VICTIM_NUM} ready (from snapshot)"
  echo "   SSH: ssh -i /root/.ssh/victim_user_key -p ${SSH_PORT} victim@localhost"
  echo "   Serial: socat -,raw,echo=0,escape=0x1d UNIX-CONNECT:${SERIAL_SOCK} # Press Ctrl+] to disconnect"
  echo "   Monitor: socat - UNIX-CONNECT:${MONITOR_SOCK}"
  echo "   PID: $(cat ${PID_FILE} 2>/dev/null || echo 'unknown')"
  echo ""
fi
