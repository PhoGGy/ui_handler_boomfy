#!/usr/bin/env python

import time
import subprocess
import sys
import select
from threading import Thread
from daemonize import Daemonize
import logging

pid="/var/run/ui_handler_boomfy.pid"

DBG = 0
INFO = 1
WARN = 2
ERR = 3

#P3 -> 1019
#P4 -> 1020

detected_global = 0

def dbg(lvl,str):
	if lvl == DBG:
		logging.debug(str)
	elif lvl == INFO:
		logging.info(str)
	elif lvl == WARN:
		logging.warning(str)
	elif lvl == ERR:
		logging.error(str)


class LEDThread(Thread): 
	def __init__(self, port): 
		Thread.__init__(self) 
		self.port = port 
		self.blink = 0
		self.quit = 0
	def run(self): 
		while self.quit != 1:
			if self.blink == 1:
				self.blink = 0
				subprocess.call("sh -c 'echo 0 > /sys/class/gpio/gpio"+ self.port +"/value'", shell=True)
			else:
				self.blink = 1
				subprocess.call("sh -c 'echo 1 > /sys/class/gpio/gpio"+ self.port +"/value'", shell=True)
			time.sleep(1)
	def stop(self):
		self.quit = 1

class ButtonThread(Thread): 
	def __init__(self, port): 
		Thread.__init__(self) 
		self.port = port 
		self.quit = 0
	def run(self): 
		global detected_global
		while self.quit != 1:
			res = subprocess.check_output("cat /sys/class/gpio/gpio"+ self.port +"/value", shell=True)
			dbg(DBG,res)
			if res == b'0\n':	#LOW ACTIVE
				detected_global = 1
			time.sleep(1)
	def stop(self):
		self.quit = 1

class LED:
	def __init__(self, port):
		self.port = port
		self.t = LEDThread(port) 
		subprocess.call("sh -c 'echo "+ self.port +" > /sys/class/gpio/unexport'", shell=True)
		subprocess.call("sh -c 'echo "+ self.port +" > /sys/class/gpio/export'", shell=True)
		subprocess.call("sh -c 'echo out > /sys/class/gpio/gpio"+ self.port +"/direction'", shell=True)
	def on(self):
		if self.t.is_alive():
			self.t.stop()
		subprocess.call("sh -c 'echo 0 > /sys/class/gpio/gpio"+ self.port +"/value'", shell=True)
	def off(self):
		if self.t.is_alive():
			self.t.stop()
		subprocess.call("sh -c 'echo 1 > /sys/class/gpio/gpio"+ self.port +"/value'", shell=True)
	def blink(self):
		try:
			self.t.start()
		except:
			dbg(INFO,"LED blink Thread already running")
	def cleanup(self):
		subprocess.call("sh -c 'echo "+ self.port +" > /sys/class/gpio/unexport'", shell=True)

class Button:
	
	def __init__(self, port):
		self.port = port
		self.t = ButtonThread(port)
		subprocess.call("sh -c 'echo "+ self.port +" > /sys/class/gpio/unexport'", shell=True)
		subprocess.call("sh -c 'echo "+ self.port +" > /sys/class/gpio/export'", shell=True)
		subprocess.call("sh -c 'echo out > /sys/class/gpio/gpio"+ self.port +"/direction'", shell=True)
		self.t.start()
	#def is_detected(self):
	#	global detected_global
	#	if detected_global == 1:
	#		detected_global = 0
	#		return 1
	#	else:
	#		return 0
	def cleanup(self):
		self.t.stop()
		subprocess.call("sh -c 'echo "+ self.port +" > /sys/class/gpio/unexport'", shell=True)

class ConnectThread(Thread):
	MODE_SERVER = 0
	MODE_CLIENT = 1
	MODE_INTERNET = 2

	def __init__(self): 
		Thread.__init__(self) 
		self.cur_mode = ConnectThread.MODE_SERVER
		self.req_mode = ConnectThread.MODE_SERVER
		self.status = -1 
		self.quit = 0
		self.process = None
		self.init = 0
		self.connected = 0
	def run(self): 
		
		dbg(DBG,"CT: ConnectThread started")
		self.connected = 0
		if self.process == None:
			dbg(DBG,"CT: No Process running")
		else:
			dbg(DBG,"CT: Running Process killed")
			self.process.kill()
		self.process = subprocess.Popen(["ifup", "wlan0=server"],)
		dbg(DBG,"CT: ifup=server called")
		self.cur_mode = self.req_mode
		self.init = 0
		dbg(DBG,"CT: Startup -> Server")
		
		while self.quit != 1:
			if self.cur_mode == ConnectThread.MODE_SERVER:
				if self.req_mode == ConnectThread.MODE_SERVER:	#stay here
					if self.init == 0:
						self.connected = 0
						self.status = self.process.poll()
						if self.status == None:	#ifup=server still running
							dbg(DBG,"CT: ifup=server still running")
						elif self.status == 0:	#completed successfully
							dbg(DBG,"CT: Server Init successfull")
							self.init = 1
						else:			#error
							dbg(ERR,"CT: Error in ifup=server")
							dbg(DBG,"CT: Calling ifdown and ifup=server")
							self.status = subprocess.call(["ifdown", "wlan0"])
							dbg(DBG,"CT: ifdown wlan0 return: {:d}".format(self.status))
							self.process = subprocess.Popen(["ifup", "wlan0=server"],)
					else:
						self.connected = 1		#nothing to do
						dbg(DBG,"CT: server established")
				elif self.req_mode == ConnectThread.MODE_CLIENT:
					self.connected = 0
					if self.process == None:
						dbg(DBG,"CT: No Process running")
					else:
						dbg(DBG,"CT: Running Process killed")
						self.process.kill()
					self.status = subprocess.call(["ifdown", "wlan0"])
					dbg(DBG,"CT: ifdown wlan0 return: {:d}".format(self.status))	
					self.process = subprocess.Popen(["ifup", "wlan0=client"],)
					dbg(DBG,"CT: ifup=client called")
					self.cur_mode = self.req_mode
					self.init = 0
					dbg(INFO,"CT: Server -> Client")
					
				elif self.req_mode == ConnectThread.MODE_INTERNET:
					self.connected = 0
					if self.process == None:
						dbg(DBG,"CT: No Process running")
					else:
						dbg(DBG,"CT: Running Process killed")
						self.process.kill()
					self.status = subprocess.call(["ifdown", "wlan0"])
					dbg(DBG,"CT: ifdown wlan0 return: {:d}".format(self.status))
					self.process = subprocess.Popen(["ifup", "wlan0=internet"],)
					dbg(DBG,"CT: ifup=internet called")
					self.cur_mode = self.req_mode
					self.init = 0
					dbg(INFO,"CT: Server -> Internet")
			elif self.cur_mode == ConnectThread.MODE_CLIENT:
				if self.req_mode == ConnectThread.MODE_CLIENT:	#stay here
					if self.init == 0:
						self.connected = 0
						self.status = self.process.poll()
						if self.status == None:	#ifup=client still running
							dbg(DBG,"CT: ifup=client still running")
						elif self.status == 0:	#completed successfully
							dbg(DBG,"CT: Client Init successfull")
							self.init = 1
						else:			#error
							dbg(ERR,"CT: Error in ifup=client")
							dbg(DBG,"CT: Calling ifdown and ifup=client")
							self.status = subprocess.call(["ifdown", "wlan0"])
							dbg(DBG,"CT: ifdown wlan0 return: {:d}".format(self.status))
							self.process = subprocess.Popen(["ifup", "wlan0=client"],)
					else:
						output = subprocess.Popen(["wpa_cli", "status"], stdout=subprocess.PIPE).communicate()[0]	#get stdout output
						out_str = str(output)
						if "COMPLETED" in out_str:	#scanning completed
							if "ip_address=" in out_str:	#client established
								self.connected = 1#nothing to do
							else:	#restarting interface
								self.connected = 0
								dbg(WARN,"CT: no ip_address, restarting interface")
								dbg(DBG,"CT: Calling ifdown and ifup=client")
								self.status = subprocess.call(["ifdown", "wlan0"])
								dbg(DBG,"CT: ifdown wlan0 return: {:d}".format(self.status))
								self.process = subprocess.Popen(["ifup", "wlan0=client"],)
								self.init = 0
						else:
							self.connected = 0
							dbg(DBG,"CT: still scanning, waiting")
				elif self.req_mode == ConnectThread.MODE_SERVER:
					self.connected = 0
					if self.process == None:
						dbg(DBG,"CT: No Process running")
					else:
						dbg(DBG,"CT: Running Process killed")
						self.process.kill()
					self.status = subprocess.call(["ifdown", "wlan0"])
					dbg(DBG,"CT: ifdown wlan0 return: {:d}".format(self.status))
					self.process = subprocess.Popen(["ifup", "wlan0=server"],)
					dbg(DBG,"CT: ifup=server called")
					self.cur_mode = self.req_mode
					self.init = 0
					dbg(INFO,"CT: Client -> Server")
				elif self.req_mode == ConnectThread.MODE_INTERNET:
					self.connected = 0
					if self.process == None:
						dbg(DBG,"CT: No Process running")
					else:
						dbg(DBG,"CT: Running Process killed")
						self.process.kill()
					self.status = subprocess.call(["ifdown", "wlan0"])
					dbg(DBG,"CT: ifdown wlan0 return: {:d}".format(self.status))
					self.process = subprocess.Popen(["ifup", "wlan0=internet"],)
					dbg(DBG,"CT: ifup=internet called")
					self.cur_mode = self.req_mode
					self.init = 0
					dbg(INFO,"CT: Client -> Internet")
			elif self.cur_mode == ConnectThread.MODE_INTERNET:
				if self.req_mode == ConnectThread.MODE_INTERNET:	#stay here
					if self.init == 0:
						self.connected = 0
						self.status = self.process.poll()
						if self.status == None:	#ifup=internet still running
							dbg(DBG,"CT: ifup=internet still running")
						elif self.status == 0:	#completed successfully
							dbg(DBG,"CT: Internet Init successfull")
							self.init = 1
						else:			#error
							dbg(ERR,"CT: Error in ifup=internet")
							dbg(DBG,"CT: Calling ifdown and ifup=internet")
							self.status = subprocess.call(["ifdown", "wlan0"])
							dbg(DBG,"CT: ifdown wlan0 return: {:d}".format(self.status))
							self.process = subprocess.Popen(["ifup", "wlan0=internet"],)
					else:
						output = subprocess.Popen(["wpa_cli", "status"], stdout=subprocess.PIPE).communicate()[0]	#get stdout output
						out_str = str(output)
						if "COMPLETED" in out_str:	#scanning completed
							if "ip_address=" in out_str:	#internet established
								self.connected = 1#nothing to do
							else:	#restarting interface
								self.connected = 0
								dbg(WARN,"CT: no ip_address, restarting interface")
								dbg(DBG,"CT: Calling ifdown and ifup=internet")
								self.status = subprocess.call(["ifdown", "wlan0"])
								dbg(DBG,"CT: ifdown wlan0 return: {:d}".format(self.status))
								self.process = subprocess.Popen(["ifup", "wlan0=internet"],)
								self.init = 0
						else:
							self.connected = 0
							dbg(DBG,"CT: still scanning, waiting")
				elif self.req_mode == ConnectThread.MODE_SERVER:
					self.connected = 0
					if self.process == None:
						dbg(DBG,"CT: No Process running")
					else:
						dbg(DBG,"CT: Running Process killed")
						self.process.kill()
					self.status = subprocess.call(["ifdown", "wlan0"])
					dbg(DBG,"CT: ifdown wlan0 return: {:d}".format(self.status))
					self.process = subprocess.Popen(["ifup", "wlan0=server"],)
					dbg(DBG,"CT: ifup=server called")
					self.cur_mode = self.req_mode
					self.init = 0
					dbg(INFO,"CT: Internet -> Server")
				elif self.req_mode == ConnectThread.MODE_CLIENT:
					self.connected = 0
					if self.process == None:
						dbg(DBG,"CT: No Process running")
					else:
						dbg(DBG,"CT: Running Process killed")
						self.process.kill()
					self.status = subprocess.call(["ifdown", "wlan0"])
					dbg(DBG,"CT: ifdown wlan0 return: {:d}".format(self.status))
					self.process = subprocess.Popen(["ifup", "wlan0=client"],)
					dbg(DBG,"CT: ifup=client called")
					self.cur_mode = self.req_mode
					self.init = 0
					dbg(INFO,"CT: Internet -> Client")
			time.sleep(1)
				
		#quit Thread...
		while process.Poll() == None:	#process still running	
			process.kill()
			dbg(DBG,"CT: Process killed")
			time.sleep(1)
		
		
	def set_mode(self, mode):	#set Server or client mode
		self.connected = 0
		if mode == ConnectThread.MODE_SERVER:
			self.req_mode = mode
			dbg(INFO,"CT: set Server Mode")
		elif mode == ConnectThread.MODE_CLIENT:
			self.req_mode = mode
			dbg(INFO,"CT: set Client Mode")
		elif mode == ConnectThread.MODE_INTERNET:
			self.req_mode = mode
			dbg(INFO,"CT: set Internet Mode")
		else:
			dbg(WARN,"CT: Wrong Connect Mode: {}".format(mode))

	def get_mode(self):
		return self.cur_mode

	def get_connected(self):
		return self.connected
	
	def stop(self):
		self.quit = 1

def main():
	led_red_port = "1022" #"XIO-P6"
	led_green_port = "1023" #"XIO-P7"
	button_port = "1016" #"XIO-P0"
	quit = 0

	try:	#catching all exceptions to clean up before closing
		state = "STARTUP"
		button = 0	
		logging.basicConfig(filename='/var/log/ui_handler_boomfy.log',level=logging.DEBUG,format='%(asctime)s %(levelname)-8s %(message)s', datefmt='%H:%M:%S')

		dbg(INFO,"MAIN: Starting UI Handler")

		led_green = LED(led_green_port)
		led_red = LED(led_red_port)
		button = Button(button_port)
		connectthread = ConnectThread()
		connectthread.start()

		dbg(DBG,"MAIN: ConnectThread started")

		while quit == 0:
			time.sleep(1)
			if state == "STARTUP":
				dbg(INFO,"MAIN: Startup state")
				led_red.on()	#turn on red and green
				led_green.on()
				time.sleep(1)
				state = "INIT_SERVER"
				connectthread.set_mode(ConnectThread.MODE_SERVER)
				dbg(INFO,"MAIN: Init Server state")
				led_red.blink()	#blink red
				led_green.off()
			elif state == "INIT_SERVER":

				if connectthread.get_connected() == 1:	#connected
					led_red.on() #light red
					led_green.off()
					detected_global = 0 #ignore button presses till here
					dbg(DBG,"MAIN: start snapcast server")
					dbg(DBG,"MAIN: restart snapcast client")
					dbg(DBG,"MAIN: start pulseaudio")
					dbg(DBG,"MAIN: enable bt-adapter")
					subprocess.call(["/etc/init.d/S99snapserver", "restart"])
					subprocess.call(["/etc/init.d/S99snapclient", "restart"])
					subprocess.call(["/etc/init.d/S50pulseaudio", "restart"])
					subprocess.call("su -c /home/chip/bt_adapter_enable", shell=True)
					dbg(INFO,"MAIN: Server State")
					state = "SERVER"
				else:
					dbg(DBG,"MAIN: .")

			elif state == "SERVER":
				#stay here till button press
				if detected_global==1:
					detected_global = 0
					dbg(INFO,"MAIN: Button Pressed")
					dbg(INFO,"MAIN: Switch to Client Mode")
					state = "INIT_CLIENT"
					connectthread.set_mode(ConnectThread.MODE_CLIENT)
					led_green.blink() #blink green
					led_red.off()
					dbg(DBG,"MAIN: stop snapcast server")
					subprocess.call(["/etc/init.d/S99snapserver", "stop"])
				else:
					#inside Server state
					a=0
			elif state == "INIT_CLIENT":

				if detected_global==1:
					detected_global = 0
					dbg(INFO,"MAIN: Button Pressed")
					dbg(INFO,"MAIN: Switch to Server Mode")
					state = "INIT_SERVER"
					connectthread.set_mode(ConnectThread.MODE_SERVER)
					dbg(INFO,"MAIN: Init Server state")
					led_red.blink() #blink red
					led_green.off()
				else:
					if connectthread.get_connected() == 1:	#connected

						led_red.off() #light green
						led_green.on()
						detected_global = 0 #ignore button presses till here
						dbg(DBG,"MAIN: restart snapcast client")
						dbg(DBG,"MAIN: stop pulseaudio")
						dbg(DBG,"MAIN: disable bt-adapter")
						subprocess.call(["/etc/init.d/S99snapclient", "restart"])
						subprocess.call(["/etc/init.d/S50pulseaudio", "stop"])
						subprocess.call("su -c /home/chip/bt_adapter_disable", shell=True)
						dbg(INFO,"MAIN: Client State")
						state = "CLIENT"
					else:
						dbg(DBG,"MAIN: .")
			elif state == "CLIENT":
				if detected_global==1:		#stay here till button press
					detected_global = 0
					dbg(INFO,"MAIN: Button Pressed")
					dbg(INFO,"MAIN: Switch to Server Mode")
					state = "INIT_SERVER"
					connectthread.set_mode(ConnectThread.MODE_SERVER)
					led_red.blink() #blink red
					led_green.off()
				else:
					#inside Client state
					a=0
			else:
				#Dunno
				a=6
	except:
		dbg(ERR,"MAIN: caught exception: quitting...")
		dbg(ERR,"MAIN: Unexpected error: {}".format(sys.exc_info()[0]))
		led_green.cleanup()
		led_red.cleanup()
		button.cleanup()
		
daemon = Daemonize(app="ui_handler_boomfy", pid=pid, action=main)
daemon.start()
