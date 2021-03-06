#!/usr/bin/python
import os
import io
import csv
import time
import fcntl
import string
import config
from time import sleep
from smtp_service import Mailer
from mariadb_service import Mariadb
from thread_service import ThreadCount

# ATLAS_I2C TEMPERATURE SENSOR CLASS
class atlas_i2c:
    default_bus = 1
    long_timeout = 9
    short_timeout = .5
    default_address = 102
    def __init__(self, address=default_address, bus=default_bus):
        self.file_read = io.open("/dev/i2c-" + str(bus), "rb", buffering=0)
        self.file_write = io.open("/dev/i2c-" + str(bus), "wb", buffering=0)
        self.set_i2c_address(address)
    def set_i2c_address(self, addr):
        I2C_SLAVE = 0x703
        fcntl.ioctl(self.file_read, I2C_SLAVE, addr)
        fcntl.ioctl(self.file_write, I2C_SLAVE, addr)
    def write(self, string):
        string += "\00"
        self.file_write.write(string)
    def read(self, num_of_bytes=31):
        res = self.file_read.read(num_of_bytes)
        response = filter(lambda x: x != '\x00', res)
        if(ord(response[0]) == 1):
            char_list = map(lambda x: chr(ord(x) & ~0x80), list(response[1:]))
            return ''.join(char_list)
        else:
            return "Error: " + str(ord(response[0]))
    def query(self, string):
        self.write(string)
        if(string.upper().startswith("R")):
            sleep(self.long_timeout)
        elif(string.upper().startswith("CAL")):
            sleep(self.long_timeout)
        elif((string.upper().startswith("SLEEP"))):
            return "sleep mode"
        else:
            sleep(self.short_timeout)
        return self.read()
    def close(self):
        self.file_read.close()
        self.file_write.close()


# CREATE TABLE FUNCTION
def create_mariadb():
    try:
        db = Mariadb()
        db.execute("CREATE TABLE IF NOT EXISTS temperature_tbl"
                "(id INT(20) NOT NULL AUTO_INCREMENT,"
                "degree VARCHAR(8),"
                "status VARCHAR(8),"
                "date VARCHAR(24),"
                "PRIMARY KEY(id));")
        print "\t\tCREATE TABLE"
    except:
        pass
    return

# INSERT DATA TO DB FUNCTION
def insert_mariadb(data, alert):
    db = Mariadb()
    db.execute('INSERT INTO temperature_tbl (degree, status, date) VALUES ("{}", "{}", "{}");'.format(data, str(alert), str(time.ctime())))
    return

# CREATE CSV FILE FUNCTION
def csv_filename():
    return os.path.abspath('daily_reports/report-' + str(time.strftime('%d')) + '.csv')

# WRITE CSV FILE FUNCTION
def write_csv_file():
    db = Mariadb()
    query = db.query('SELECT * FROM temperature_tbl;')
    csv_file = open(csv_filename(), 'a')
    csv_attachment = csv.writer(csv_file)
    csv_attachment.writerows(query)
    csv_file.close()
    return

# SEND EMAIL FUNCTION
def send_email(msg, email):
    mailer = Mailer()
    date_msg = msg[msg.find('\n') + 1:len(msg)] + '<br>'
    degree_msg = msg[0:msg.find('$')]
    mailer.send_report(str(time.strftime('%m/%d/%Y')), date_msg, degree_msg, email, csv_filename())
    return

# TEMPERATURE CHECK FUNCTION
def check_temperature(temp_msg):
    date_time = str(time.ctime())
    sensor_device = atlas_i2c()
    temp_int = float(sensor_device.query("R"))
    daily_report_time = time.strftime('%H:%M', time.localtime())
    if float(temp_int) >= config.temp_ini['max']:
        msg = str("MAXIMUM TEMPERATURE: %s$\nDATE & TIME: %s" % (temp_msg, date_time))
    elif float(temp_int) <= config.temp_ini['min']:
        msg = str("MINIMUM TEMPERATURE: %s$\nDATE & TIME: %s" % (temp_msg, date_time))
    else:
        msg = str("NORMAL TEMPERATURE: %s $\nDATE & TIME: %s" % (temp_msg, date_time))
    return msg


# STOP OR CONTINUE PROGRAM FUNCTION
def stop_atlas(message, device_info, device_status, delay_time, temp_msg):
    running = True
    while running:
        try:
            user_input = str(raw_input(message))
        except:
            config.print_info(device_info, device_status, delay_time, temp_msg, "OFF")
            os.system('cd /home/pi/RaspberryPi/src; crontab -r')
            print "\t\t\tGOODBYE!\n"
            running = False
        else:
            if user_input == '1':
                config.print_info(device_info, device_status, delay_time, temp_msg, "OFF")
                os.system('cd /home/pi/RaspberryPi/src; crontab -r')
                print "\t\t\tGOODBYE!"
                running = False
            else:
                config.print_info(device_info, device_status, delay_time, temp_msg, " ON")
                running = True
                break
    return running


# MAIN FUNCTION
def main():
    mdb = create_mariadb()
    thread = ThreadCount()
    sensor_device = atlas_i2c()
    delay_time = atlas_i2c.long_timeout
    device_info = string.split(sensor_device.query("I"), ",")[1]
    device_status = sensor_device.query("STATUS")[1:len(sensor_device.query("STATUS"))]
    is_running = True
    is_thread = True
    while is_running:
        try:
            print_device = str(sensor_device.query("R")) + config.temp_ini['degree']
            temp_msg = check_temperature(print_device)
            config.print_info(device_info, device_status, delay_time, temp_msg, " ON")
            if temp_msg[0:6] == "NORMAL":
                insert_mariadb(print_device, "NORMAL")
            else:
                insert_mariadb(print_device, "ALERT")
                write_csv_file()
                send_email(temp_msg, 'ALERT REPORT')
                while is_thread:
                    is_thread = thread.run()
        except KeyboardInterrupt:
            is_running = stop_atlas("\t\tPRESS '1' TO QUIT"
                                    "\n\t\tPRESS 'ANY KEY' TO CONTINUE"
                                    "\n\t\tENTER: ",
                                    device_info, device_status, delay_time, temp_msg)


if __name__ == '__main__':
    main()
