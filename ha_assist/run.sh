#!/usr/bin/with-contenv bashio
# ==============================================================================
# HA Assist - Entrypoint
# ==============================================================================

# Read add-on options
LOG_LEVEL=$(bashio::config 'log_level')

bashio::log.info "Starting HA Assist..."
bashio::log.info "Log level: ${LOG_LEVEL}"

# ----- Start the assistant -----
exec python3 /assist.py
