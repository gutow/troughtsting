def troughctl(CTLPipe,DATAPipe):
    """
    Will run as separate process taking in commands through a pipe and returning data
    on demand through a second pipe.
    Iteration 1, collects data into a fifo and watches barrier position.
    :param Pipe CTLPipe: pipe commands come in on and messages go out on.
    :param Pipe DATAPipe: pipe data is sent out on
    """
    import time
    import numpy as np
    from collections import deque
    from multiprocessing import Pipe
    from piplates import DAQC2plate as DAQC2

    def barrier_at_limit_check(openlimit, closelimit):
        """
        Checks if barrier is at or beyond limit and stops barrier if it is moving
        in a direction that would make it worse.
        :param float openlimit: lowest voltage allowed for opening
        :param float closelimit: highest voltage allowed for closing

        Returns
        =======
        True or False. If True also shuts down power to barrier
        """

        direction = 0  # -1 closing, 0 stopped, 1 openning.
        if (DAQC2.getDAC(0, 0) >= 2.5):
            direction = -1
        else:
            direction = 1
        position = DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1)
        if (position >= closelimit) and (direction == -1):
            DAQC2.clrDOUTbit(0, 0)  # switch off power/stop barriers
            return True
        if (position <= openlimit) and (direction == 1):
            DAQC2.clrDOUTbit(0, 0)  # switch off power/stop barriers
            return True
        return False

    def motorcal(barriermin, barriermax):
        '''
        :param float barriermin: minimum voltage for barrier (do not open more).
        :param float barriermax: maximum voltage for barrier (do not close more).
        :returns float maxclose: DAC setting for maximum close speed.
        :returns float minclose: DAC setting for minimum close speed.
        :returns float startclose: DAC setting providing minimum voltage to start closing.
        :returns float maxopen: DAC setting for maximum close speed.
        :returns float minopen: DAC setting for minimum close speed.
        :returns float startopen: DAC setting providing minimum voltage to start opening.
        '''

        import os, time
        # Since this runs in a tight loop needs to take over watching barriers.
        # Check if a trough controller is registered at /tmp/troughctl.pid.
        # If one is store it's pid and replace with own. Will revert on exit without
        # crashing.
        pidpath = '/tmp/troughctl.pid'
        ctlpid = None
        if os.path.exists(pidpath):
            file = open(pidpath, 'r')
            ctlpid = int(file.readline())
            file.close()
        pid = os.getpid()
        # print(str(pid))
        file = open(pidpath, 'w')
        file.write(str(pid) + '\n')
        file.close()
        # Do not proceed until this file exists on the file system
        while not os.path.exists(pidpath):
            pass  # just waiting for file system to catch up.
        # Read it to make sure
        file = open(pidpath, 'r')
        checkpid = file.readline()
        file.close()
        if int(checkpid) != pid:
            raise FileNotFoundError('Checkpid = ' + checkpid + ', but should = ' + str(pid))

        # Set base values
        maxclose = 4
        minclose = 2.6
        startclose = 2.6
        maxopen = 0
        minopen = 2.4
        startopen = 2.4
        # Calibrate the barrier. This assumes a DAQC2 pi-plate is the controlling interface.
        # First move to fully open.
        print('Moving to fully open...')
        position = round(DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1), 2)  # not stable past 2 decimals
        if position > barriermin:
            # need to open some
            atlimit = False
            DAQC2.setDAC(0, 0, maxopen)  # set fast open
            DAQC2.setDOUTbit(0, 0)  # turn on power/start barriers
            time.sleep(1)
            while not atlimit:
                atlimit = barrier_at_limit_check(barriermin, barriermax)
        # Get rid of any hysteresis in the close direction
        print('Removing close hysteresis...')
        position = round(DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1), 2)  # not stable past 2 decimals
        stoppos = position + 0.05
        if stoppos > barriermax:
            stoppos = barriermax
        DAQC2.setDAC(0, 0, maxclose)  # set fast close
        DAQC2.setDOUTbit(0, 0)  # turn on power/start barriers
        time.sleep(1)
        atlimit = False
        while not atlimit:
            atlimit = barrier_at_limit_check(barriermin, stoppos)
        # Find closing stall voltage
        print('Finding closing stall voltage...')
        oldposition = round(DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1), 2)  # not stable past 2 decimals
        DAQC2.setDAC(0, 0, maxclose)  # set fast close
        DAQC2.setDOUTbit(0, 0)  # turn on power/start barriers
        testclose = maxclose
        time.sleep(2)
        atlimit = False
        while not atlimit:
            atlimit = barrier_at_limit_check(barriermin, barriermax)
            position = round(DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1), 2)  # not stable past 2 decimals
            #        if position > 6.5:
            #            print ('old: '+str(oldposition)+' position: '+str(position))
            if (position - oldposition) < 0.01:
                # because there can be noise take a new reading and check again
                position = round(DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1), 2)  # not stable past 2 decimals
                if (position - oldposition) < 0.01:
                    minclose = testclose
                    atlimit = True
                    DAQC2.clrDOUTbit(0, 0)
            oldposition = position
            testclose = testclose - 0.05
            DAQC2.setDAC(0, 0, testclose)
            time.sleep(2)

        # Find minimum closing start voltage
        print('Finding minimum closing start voltage...')
        oldposition = round(DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1), 2)  # not stable past 2 decimals
        startclose = minclose
        atlimit = False
        while not atlimit:
            atlimit = barrier_at_limit_check(barriermin, barriermax)
            DAQC2.setDAC(0, 0, startclose)
            DAQC2.setDOUTbit(0, 0)  # turn on power/start barriers
            time.sleep(2)
            position = round(DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1), 2)  # not stable past 2 decimals
            if (position - oldposition) < 0.01:
                # because there can be noise take a new reading and check again
                position = round(DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1), 2)  # not stable past 2 decimals
                if (position - oldposition) < 0.01:
                    startclose = startclose + 0.05
            else:
                atlimit = True
                DAQC2.clrDOUTbit(0, 0)
                startclose = startclose + 0.05  # To provide a margin.
        # Move to fully closed
        print('Moving to fully closed...')
        position = round(DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1), 2)  # not stable past 2 decimals
        if position < barriermax:
            # need to close some
            atlimit = False
            DAQC2.setDAC(0, 0, maxclose)  # set fast close
            DAQC2.setDOUTbit(0, 0)  # turn on power/start barriers
            time.sleep(1)
            while not atlimit:
                atlimit = barrier_at_limit_check(barriermin, barriermax)

        # Get rid of any hysteresis in the open direction
        print('Removing open hysteresis...')
        position = round(DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1), 2)  # not stable past 2 decimals
        stoppos = position - 0.05
        if stoppos < barriermin:
            stoppos = barriermin
        DAQC2.setDAC(0, 0, maxopen)  # set fast close
        DAQC2.setDOUTbit(0, 0)  # turn on power/start barriers
        time.sleep(1)
        atlimit = False
        while not atlimit:
            atlimit = barrier_at_limit_check(stoppos, barriermax)

        # Find openning stall voltage
        print('Finding openning stall voltage...')
        oldposition = round(DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1), 2)  # not stable past 2 decimals
        DAQC2.setDAC(0, 0, maxopen)  # set fast close
        DAQC2.setDOUTbit(0, 0)  # turn on power/start barriers
        testopen = maxopen
        time.sleep(2)
        atlimit = False
        while not atlimit:
            atlimit = barrier_at_limit_check(barriermin, barriermax)
            position = round(DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1), 2)  # not stable past 2 decimals
            #        if position > 6.5:
            #            print ('old: '+str(oldposition)+' position: '+str(position))
            if (oldposition - position) < 0.01:
                # because there can be noise take a new reading and check again
                position = round(DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1), 2)  # not stable past 2 decimals
                if (oldposition - position) < 0.01:
                    minopen = testopen
                    atlimit = True
                    DAQC2.clrDOUTbit(0, 0)
            oldposition = position
            testopen = testopen + 0.05
            DAQC2.setDAC(0, 0, testopen)
            time.sleep(2)

        # Find minimum opening start voltage
        print('Finding minimum openning start voltage...')
        oldposition = round(DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1), 2)  # not stable past 2 decimals
        startopen = minopen
        atlimit = False
        while not atlimit:
            atlimit = barrier_at_limit_check(barriermin, barriermax)
            DAQC2.setDAC(0, 0, startopen)
            DAQC2.setDOUTbit(0, 0)  # turn on power/start barriers
            time.sleep(2)
            position = round(DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1), 2)  # not stable past 2 decimals
            if (oldposition - position) < 0.01:
                # because there can be noise take a new reading and check again
                position = round(DAQC2.getADC(0, 0) - DAQC2.getADC(0, 1), 2)  # not stable past 2 decimals
                if (oldposition - position) < 0.01:
                    startopen = startopen - 0.05
            else:
                atlimit = True
                DAQC2.clrDOUTbit(0, 0)
                startopen = startopen - 0.05  # To provide a margin.

        # Return control to previous trough controller
        if ctlpid is not None:
            file = open(pidpath, 'w')
            file.write(str(ctlpid) + '\n')
            file.close()
        elif os.path.exists(pidpath):
            os.remove(pidpath)
        elif os.path.exists(pidpath):  # double check
            os.remove(pidpath)

        # Return the results
        return (maxclose, minclose, startclose, maxopen, minopen, startopen)

    def calcDAC_V(speed, direction, maxclose, minclose, maxopen, minopen):
        '''
        :param float speed: fraction of maximum speed
        :param int direction: -1 close, 0 don't move, 1 open
        :param float maxclose: DAC V for maximum close speed
        :param float minclose: DAC V for minimum close speed
        :param float maxopen: DAC V for maximum open speed
        :param float minopen: DAC V for minimum open speed

        :return float DAC_V:
        '''
        DAC_V = (minclose+minopen)/2 # default to not moving
        if direction == -1:
            DAC_V = (maxclose-minclose)*speed + minclose
        if direction == 1:
            DAC_V = (maxopen - minopen)*speed + minopen
        return DAC_V

    poshigh = []
    poslow = []
    balhigh = []
    ballow = []
    thermhigh = []
    thermlow = []

    pos_V = deque(maxlen=5)
    pos_std = deque(maxlen=5)
    bal_V = deque(maxlen=5)
    bal_std = deque(maxlen=5)
    therm_V = deque(maxlen=5)
    therm_std = deque(maxlen=5)
    time_stamp = deque(maxlen=5)
    cmd_deque = deque()

    timedelta = 0.500  # seconds
    openmin = 0.05 # minimum voltage allowed when opening.
    openlimit = openmin
    closemax = 7.78 # maximum voltage allowed when closing.
    closelimit = closemax
    maxcloseV, mincloseV, startcloseV, maxopenV, minopenV, startopenV = motorcal(openlimit, closelimit)
    speed = 0 # 0 to 1 fraction of maximum speed.
    direction = 0 # -1 close, 0 don't move, 1 open
    run = True
    while run:
        starttime = time.time()
        stopat = starttime + timedelta - 0.200  # leave 200 ms for communications and control
        while (time.time() < stopat):
            poslow.append(DAQC2.getADC(0, 1))
            poshigh.append(DAQC2.getADC(0, 0))
            ballow.append(DAQC2.getADC(0, 3))
            balhigh.append(DAQC2.getADC(0, 2))
            thermlow.append(DAQC2.getADC(0, 4))
            thermhigh.append(DAQC2.getADC(0, 5))
        time_stamp.append((starttime + stopat) / 2)
        # position
        ndata = len(poshigh)
        high = np.array(poshigh, dtype=np.float64)
        low = np.array(poslow, dtype=np.float64)
        vals = high - low
        avg = (np.sum(vals)) / ndata
        stdev = np.std(vals, ddof=1, dtype=np.float64)
        stdev_avg = stdev / np.sqrt(float(ndata))
        pos_V.append(avg)
        pos_std.append(stdev_avg)
        # balance
        ndata = len(balhigh)
        high = np.array(balhigh, dtype=np.float64)
        low = np.array(ballow, dtype=np.float64)
        vals = high - low
        avg = (np.sum(vals)) / ndata
        stdev = np.std(vals, ddof=1, dtype=np.float64)
        stdev_avg = stdev / np.sqrt(float(ndata))
        bal_V.append(avg)
        bal_std.append(stdev_avg)
        # thermistor
        ndata = len(thermhigh)
        high = np.array(thermhigh, dtype=np.float64)
        low = np.array(thermlow, dtype=np.float64)
        vals = high - low
        avg = (np.sum(vals)) / ndata
        stdev = np.std(vals, ddof=1, dtype=np.float64)
        stdev_avg = stdev / np.sqrt(float(ndata))
        therm_V.append(avg)
        therm_std.append(stdev_avg)

        # Check barrier positions
        if openlimit < openmin:
            openlimit = openmin
        if closelimit > closemax:
            closelimit = closemax
        barrier_at_limit = barrier_at_limit_check(openlimit,closelimit)
        # TODO: Send warnings and error messages
        # Check command pipe and update command queue
        if CTLPipe.poll():
            for i in range(0,CTLPipe.qsize()):
                cmd_deque.append(CTLPipe.recv())
        # Each command is a python list.
        #    element 1: cmd name (string)
        #    element 2: single command parameter (number or string)
        # Execute commands in queue
        while len(cmd_deque) > 0:
            cmd = cmd_deque.popleft()
            # execute the command
            if cmd[0] == 'Stop':
                DAQC2.clrDOUTbit(0, 0)  # switch off power/stop barriers
            elif cmd[0] == 'Send':
                # send current contents of the data deques
                DATAPipe.send(time_stamp, pos_V, pos_std, bal_V, bal_std,
                              therm_V, therm_std)
                # purge the sent content
                time_stamp.clear()
                pos_V.clear()
                pos_std.clear()
                bal_V.clear()
                bal_std.clear()
                therm_V.clear()
                therm_std.clear()
            elif cmd[0] == 'Start':
                # start barriers moving using current direction and speed
                if speed > 1:
                    speed = 1
                if speed < 0:
                    speed = 0
                if (direction != -1) and (direction != 0) and (direction != 1):
                    direction = 0
                DAC_V = calcDAC_V(speed,direction,maxcloseV,mincloseV,maxopenV,minopenV)
                if (DAC_V > startopenV) and (DAC_V < startcloseV) and (direction != 0):
                    # need a boost to start moving
                    if speed == 1:
                        DAQC2.setDAC(0,0,startcloseV)
                    else:
                        DAQC2.setDAC(0,0,startopenV)
                    DAQC2.setDOUTbit(0, 0)
                    time.sleep(0.25)
                DAQC2.setDAC(0, 0, DAC_V)
            elif cmd[0] == 'Direction':
                # set the direction
                direction = cmd[1]
                if (direction != -1) and (direction != 0) and (direction != 1):
                    direction = 0
            elif cmd[0] == 'Speed':
                # set the speed
                speed = cmd[1]
                if speed > 1:
                    speed = 1
                if speed < 0:
                    speed = 0
            elif cmd[0] == 'MoveTo':
                # adjust direction if necessary
                # set the stop position
                # start the barriers
            elif cmd[0] == 'MotorCal':
                # calibrate the voltages for starting motor and speeds
            elif cmd[0] == 'ConstPi':
                # maintain a constant pressure
                # not yet implemented
        # Delay if have not used up all 200 ms
        used = time.time() - starttime
        if used < 0.495:
            time.sleep(0.495 - used)
