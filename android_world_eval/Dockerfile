# Credits to https://github.com/amrsa1/Android-Emulator-image

FROM budtmo/docker-android:emulator_14.0


WORKDIR /app

#=========================
# Copying Scripts to root
#=========================
COPY . /app


RUN chmod a+x docker_setup/start_emu.sh && \
    chmod a+x docker_setup/start_emu_headless.sh && \
    chmod a+x docker_setup/entrypoint.sh

#====================================
# Install dependencies
#====================================
#=======================
# framework entry point
#=======================
ENTRYPOINT [ "./docker_setup/entrypoint.sh" ]
