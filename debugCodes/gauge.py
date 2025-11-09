#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import time


# Opción 1: Usando RPi.GPIO (versión robusta)
def rain_gauge_rpi_gpio():
    import RPi.GPIO as GPIO

    RAIN_PIN = 6  # Pin BCM donde está el reed switch
    MM_PER_TICK = 0.2794  # mm de lluvia por pulso
    rain_count = 0

    def rain_pulse(channel):
        nonlocal rain_count
        rain_count += 1
        print(
            f"Pulso detectado! Total: {rain_count} -> {rain_count * MM_PER_TICK:.3f} mm"
        )

    print("=== MEDIDOR DE LLUVIA (RPi.GPIO) ===")

    try:
        # IMPORTANTE: Limpiar GPIO antes de configurar
        GPIO.cleanup()
        print("✓ GPIO limpiado")

        # Configurar modo y pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(RAIN_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        print(f"✓ Pin {RAIN_PIN} configurado como INPUT con pull-up")

        # Verificar estado inicial del pin
        initial_state = GPIO.input(RAIN_PIN)
        print(
            f"✓ Estado inicial del pin: {initial_state} ({'HIGH' if initial_state else 'LOW'})"
        )

        # Añadir detección de flanco con manejo de errores
        try:
            GPIO.add_event_detect(
                RAIN_PIN, GPIO.FALLING, callback=rain_pulse, bouncetime=300
            )
            print("✓ Detección de pulsos configurada")
        except RuntimeError as e:
            print(f"✗ Error configurando detección: {e}")
            print("  Posibles soluciones:")
            print("  1. sudo pkill -f python (matar otros procesos)")
            print("  2. Reiniciar la Pi")
            print("  3. Usar gpiozero (opción 2)")
            return False

        print("\nMidiendo lluvia... (Ctrl+C para salir)")
        print("Toca el sensor para probar")

        try:
            while True:
                time.sleep(1)
                # Mostrar estado del pin cada 10 segundos para debug
                if int(time.time()) % 10 == 0:
                    state = GPIO.input(RAIN_PIN)
                    print(f"[DEBUG] Pin state: {state}, Rain count: {rain_count}")

        except KeyboardInterrupt:
            print(f"\nTotal lluvia acumulada: {rain_count * MM_PER_TICK:.3f} mm")

    except Exception as e:
        print(f"Error general: {e}")
        return False
    finally:
        GPIO.cleanup()
        print("GPIO limpiado")

    return True


# Opción 2: Usando gpiozero (más robusto)
def rain_gauge_gpiozero():
    try:
        from gpiozero import Button, Device
        from gpiozero.pins.pigpio import PiGPIOFactory
    except ImportError:
        print("Error: gpiozero no está instalado")
        print("Instalar con: pip install gpiozero pigpio")
        return False

    RAIN_PIN = 6  # Pin BCM donde está el reed switch
    MM_PER_TICK = 0.2794  # mm de lluvia por pulso
    rain_count = 0

    def rain_pulse():
        nonlocal rain_count
        rain_count += 1
        print(
            f"Pulso detectado! Total: {rain_count} -> {rain_count * MM_PER_TICK:.3f} mm"
        )

    print("=== MEDIDOR DE LLUVIA (GPIOZERO) ===")

    try:
        # Usar pigpio factory para mayor robustez
        Device.pin_factory = PiGPIOFactory()
        print("✓ PiGPIO factory configurado")

        # Configurar sensor como button
        rain_sensor = Button(
            RAIN_PIN,
            pull_up=True,  # Reed switch conectado a masa
            bounce_time=0.01,  # 300ms debounce
        )
        print(f"✓ Sensor en pin {RAIN_PIN} configurado")

        # Configurar callback para flanco descendente
        rain_sensor.when_pressed = rain_pulse
        print("✓ Detección de pulsos configurada")

        # Verificar estado inicial
        print(f"✓ Estado inicial: {'HIGH' if rain_sensor.is_pressed else 'LOW'}")

        print("\nMidiendo lluvia... (Ctrl+C para salir)")
        print("Toca el sensor para probar")

        try:
            start_time = time.time()
            while True:
                time.sleep(1)
                # Debug cada 10 segundos
                if int(time.time() - start_time) % 10 == 0:
                    state = "PRESSED" if rain_sensor.is_pressed else "RELEASED"
                    print(f"[DEBUG] Sensor: {state}, Rain count: {rain_count}")

        except KeyboardInterrupt:
            print(f"\nTotal lluvia acumulada: {rain_count * MM_PER_TICK:.3f} mm")

    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        try:
            rain_sensor.close()
            print("Sensor cerrado correctamente")
        except:
            pass

    return True


# Opción 3: Polling manual (siempre funciona)
def rain_gauge_polling():
    import RPi.GPIO as GPIO

    RAIN_PIN = 6  # Pin BCM donde está el reed switch
    MM_PER_TICK = 0.2794  # mm de lluvia por pulso
    rain_count = 0
    last_state = 1  # Estado anterior del pin

    print("=== MEDIDOR DE LLUVIA (POLLING) ===")

    try:
        GPIO.cleanup()
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(RAIN_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        print(f"✓ Pin {RAIN_PIN} configurado para polling")

        print("\nMidiendo lluvia por polling... (Ctrl+C para salir)")
        print("Método más lento pero 100% confiable")

        try:
            while True:
                current_state = GPIO.input(RAIN_PIN)

                # Detectar flanco descendente (1 → 0)
                if last_state == 1 and current_state == 0:
                    rain_count += 1
                    print(
                        f"Pulso detectado! Total: {rain_count} -> {rain_count * MM_PER_TICK:.3f} mm"
                    )
                    time.sleep(0.3)  # Debounce manual

                last_state = current_state
                time.sleep(0.01)  # Polling cada 10ms

        except KeyboardInterrupt:
            print(f"\nTotal lluvia acumulada: {rain_count * MM_PER_TICK:.3f} mm")

    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        GPIO.cleanup()
        print("GPIO limpiado")

    return True


# Función para verificar procesos que usen GPIO
def check_gpio_usage():
    import os
    import subprocess

    print("=== DIAGNÓSTICO GPIO ===")

    # Verificar procesos python
    try:
        result = subprocess.run(
            ["pgrep", "-f", "python"], capture_output=True, text=True
        )
        if result.stdout.strip():
            print("Procesos Python activos:")
            pids = result.stdout.strip().split("\n")
            for pid in pids:
                if pid != str(os.getpid()):  # Excluir proceso actual
                    try:
                        cmd_result = subprocess.run(
                            ["ps", "-p", pid, "-o", "cmd="],
                            capture_output=True,
                            text=True,
                        )
                        if cmd_result.stdout.strip():
                            print(f"  PID {pid}: {cmd_result.stdout.strip()}")
                    except:
                        pass
        else:
            print("✓ No hay otros procesos Python activos")
    except:
        print("No se pudo verificar procesos")

    # Verificar pigpio daemon
    try:
        result = subprocess.run(["pgrep", "pigpiod"], capture_output=True, text=True)
        if result.stdout.strip():
            print("✓ pigpiod daemon está corriendo")
        else:
            print("⚠ pigpiod daemon no está corriendo")
            print("  Para iniciarlo: sudo pigpiod")
    except:
        print("No se pudo verificar pigpiod")


def main():
    print("SOLUCIONADOR DE PROBLEMAS - MEDIDOR DE LLUVIA")
    print("=" * 50)

    # Verificar diagnóstico
    check_gpio_usage()
    print()

    while True:
        print("\nSelecciona una opción:")
        print("1. RPi.GPIO (método original corregido)")
        print("2. gpiozero (más robusto)")
        print("3. Polling manual (100% confiable)")
        print("4. Diagnóstico GPIO")
        print("5. Salir")

        choice = input("\nOpción (1-5): ").strip()

        if choice == "1":
            print("\n" + "=" * 30)
            if not rain_gauge_rpi_gpio():
                print("\nPrueba otra opción si falló")

        elif choice == "2":
            print("\n" + "=" * 30)
            if not rain_gauge_gpiozero():
                print("\nPrueba otra opción si falló")

        elif choice == "3":
            print("\n" + "=" * 30)
            rain_gauge_polling()

        elif choice == "4":
            check_gpio_usage()

        elif choice == "5":
            print("Saliendo...")
            break

        else:
            print("Opción inválida")


if __name__ == "__main__":
    main()
