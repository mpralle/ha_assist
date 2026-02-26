ARG BUILD_FROM
FROM $BUILD_FROM

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip

# Install Python dependencies
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# Copy root filesystem
COPY rootfs /

# Copy application code
COPY assist.py /
COPY jimmy_connection.py /
COPY prompts/ /prompts/
COPY steps/ /steps/
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
