import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import math
from math import *
import datetime as datetime
import warnings
from numpy import unravel_index

class PointProcessTrain:
    #training_points is a dataframe with labels: DATE_TIME (datetime format), XCOORD, YCOORD
    #xmin,xmax,ymin,ymax are in lat and long and initialized for Marion county
    #omega (w) is initialized to generic points
    #time_step selects multiplier for dt
    def __init__ (self, training_points, xgridsize = 100, ygridsize = 100, 
        xmin = -86.4619147125, xmax =  -85.60543100000002, ymin = 39.587905, ymax = 40.0099, 
        w = [.5, .1, .05], time_scale_label = '15minutes', 
        save_loc = 'Trained_Params.npz'):
        
        self._data = training_points 
        self._data_length = len(self._data) 
        self._xsize = xgridsize
        self._ysize = ygridsize
        self._xmin = xmin
        self._xmax = xmax
        self._ymin = ymin
        self._ymax = ymax

        self._w = w
        self._K = len(w)
        self._mu = np.ones([len(self._data), self._xsize, self._ysize])*0.0000001
        self._F = np.ones([len(self._data), self._xsize, self._ysize, self._K])*.1
        self._Lam = np.ones([len(self._data), self._xsize, self._ysize])*0.000000001
        self._theta = np.ones([len(self._data), self._K])*.1
        self._Gtimes = pd.DataFrame(np.zeros([xgridsize, ygridsize]))
        self._Gtimes[:] = self._data.DATE_TIME[0]
        self._LastTime = self._data.DATE_TIME[0]

        self._day = np.ones(7)*1/7
        self._hour = np.ones(24)*1/24

        self._save_out = save_loc

        self._time_scale_label = time_scale_label
        self._time_scaling_lookup = {'days': 1.15741e-5, 'hours': 0.0002777784, '15minutes': 0.001111111, 'minutes': 0.016666704, 'seconds': 1}
        self._time_scale = self._time_scaling_lookup[self._time_scale_label]

    def coord_to_grid(self, xcoord, ycoord):
        if xcoord < self._xmin:
            xcoord = self._xmin
        elif xcoord > self._xmax:
            xcoord = self._xmax

        if ycoord < self._ymin:
            ycoord = self._ymin
        elif ycoord > self._ymax:
            ycoord = self._ymax  

        xbin = int((xcoord-self._xmin)/(self._xmax-self._xmin)*(self._xsize-1))
        ybin = int((ycoord-self._ymin)/(self._ymax-self._ymin)*(self._ysize-1))
        return xbin, ybin

    def grid_to_coord(self, xbin, ybin):
        xcoord = (xbin * (self._xmax - self._xmin)) / (self._xsize -1) + self._xmin
        ycoord = (ybin * (self._ymax - self._ymin)) / (self._ysize -1) + self._ymin
        return xcoord, ycoord

    def param_update(self, event_time, last_event_time, xcoord, ycoord, 
        day_prob, hour_prob,
        Lam, F, mu, theta, Gtimes):

        # place new event in correct grid
        gx, gy = self.coord_to_grid(xcoord, ycoord)  

        # find day and hour
        curr_day = event_time.weekday()
        curr_hour = event_time.hour

        # find global time delta 
        time_delta = (event_time - last_event_time).total_seconds()*self._time_scale
        last_event_time = event_time

        # update periodic trends
        dt_day = .05
        for i in range(0, 7):
            day_prob[i] = (1-dt_day)*day_prob[i]
        day_prob[curr_day] += dt_day
        dt_hour = .005
        for i in range(0, 24):
            hour_prob[i] = (1-dt_hour)*hour_prob[i]
        hour_prob[curr_hour] += dt_hour 

        # global update of all grids
        for x in range(0, self._xsize):
            for y in range(0, self._ysize):
                for k in range(0, self._K):
                    F[x][y][k] = F[x][y][k] * np.exp(-1*self._w[k]*time_delta)
                Lam[x][y] = self.get_intensity(mu[x][y], sum(F[x][y]), hour_prob[curr_hour], day_prob[curr_day])

        # local update based on where event occurred
        dt = 0.005
        g_time_delta = (event_time - Gtimes.at[gx,gy]).total_seconds()*self._time_scale
        Gtimes.at[gx,gy] = event_time
        if Lam[gx][gy] == 0:
            Lam[gx][gy] = 1e-70
        mu[gx][gy] = mu[gx][gy] + dt * (mu[gx][gy]/Lam[gx][gy] - mu[gx][gy] * g_time_delta)
        for k in range(0, self._K):
            theta[k] = theta[k] + dt * (F[gx][gy][k]/Lam[gx][gy] - theta[k])
            F[gx][gy][k] = F[gx][gy][k] + self._w[k]*theta[k]

        return day_prob, hour_prob, Lam, F, mu, theta, Gtimes, last_event_time

    def get_intensity(self, mu_xy, sum_F_xy, hour_prob, day_prob):
        Lam_xy = (mu_xy + sum_F_xy)*hour_prob*day_prob
        return Lam_xy

    def train(self):
        for i in range(1, self._data_length):

            self._F[i] = self._F[i-1]
            self._mu[i] = self._mu[i-1]
            self._theta[i] = self._theta[i-1]

            self._day, self._hour, self._Lam[i], self._F[i], self._mu[i], self._theta[i], self._Gtimes, self._LastTime = self.param_update(
                self._data.DATE_TIME[i], self._data.DATE_TIME[i-1], self._data.XCOORD[i], self._data.YCOORD[i],
                self._day, self._hour,
                self._Lam[i], self._F[i], self._mu[i], self._theta[i], self._Gtimes)

        np.savez(self._save_out, Lam = self._Lam, theta = self._theta, w = self._w, 
            F = self._F, mu = self._mu, day_prob = self._day, hour_prob = self._hour,
            grid_times = self._Gtimes.values, time_scale = self._time_scale_label, 
            grid_info = [self._xsize, self._ysize, self._xmin, self._xmax, self._ymin, self._ymax],
            last_time = self._LastTime)

    def param_examine(self):
        for i in range(0, self._K):
            plt.plot(np.transpose(self._theta)[i], label="w = " + str(self._w[i]))
        plt.title("data points vs. theta")
        plt.legend()
        plt.show()

        print("\nHour vector: ")
        print(self._hour)
        print("Day vector: ")
        print(self._day)

    def model_hotspot_examine(self, num_points, num_hotspots = 10):
        # examine how top model cells compare to actual top cells over data used for training

        start = self._data_length - num_points
        end = self._data_length-1

        sum_intensity = sum(self._Lam[start:,:])
        print("Location and value of largest and smallest sum(Lambda): ")
        print(np.amax(sum_intensity), unravel_index(sum_intensity.argmax(), sum_intensity.shape),
            np.amin(sum_intensity), unravel_index(sum_intensity.argmin(), sum_intensity.shape))

        tot_events = np.zeros([self._xsize, self._ysize])
        for i in range(start, end):
            x, y = self.coord_to_grid(self._data.XCOORD[i], self._data.YCOORD[i])
            tot_events[x][y] = tot_events[x][y] + 1
        print("\nLocation of grid with most events:")
        print(np.amax(tot_events), unravel_index(tot_events.argmax(), tot_events.shape))

        sum_intensity_copy = np.copy(sum_intensity)
        pred_locs = []

        tot_events_copy = np.copy(tot_events)
        actual_locs = []

        for i in range(0, num_hotspots):
            indx = unravel_index(tot_events_copy.argmax(), tot_events_copy.shape)
            actual_locs.append(indx)
            tot_events_copy[indx[0]][indx[1]] = 0

        for i in range(0, num_hotspots):
            indx = unravel_index(sum_intensity_copy.argmax(), sum_intensity_copy.shape)
            pred_locs.append(indx)
            sum_intensity_copy[indx[0]][indx[1]] = 0

        print("\nHistorical time period is " + str((self._data.DATE_TIME[end] - self._data.DATE_TIME[start]).total_seconds()*self._time_scale) + " " + str(self._time_scale_label))

        print("\nTrained hotspots in real top " + str(num_hotspots))
        for i in range(0, num_hotspots):
            if pred_locs[i] in actual_locs:
                predicted_number = sum_intensity[pred_locs[i][0]][pred_locs[i][1]]*(1/num_points*(self._data.DATE_TIME[end]-self._data.DATE_TIME[start]).total_seconds()*self._time_scale)
                print("Grid: " + str(pred_locs[i]) +", Model: "+ str(predicted_number)+", Real: "+ str(int(tot_events[pred_locs[i][0]][pred_locs[i][1]])))

        print("\nTrained hotstpots not in real top " + str(num_hotspots))
        for i in range(0, num_hotspots):
            if pred_locs[i] not in actual_locs:
                predicted_number = sum_intensity[pred_locs[i][0]][pred_locs[i][1]]*(1/num_points*(self._data.DATE_TIME[end]-self._data.DATE_TIME[start]).total_seconds()*self._time_scale)
                print("Grid: " + str(pred_locs[i]) +", Model: "+ str(predicted_number)+", Real: "+ str(int(tot_events[pred_locs[i][0]][pred_locs[i][1]])))

        print("\nReal top " + str(num_hotspots) +" hotspots not in trained model")
        for i in range(0, num_hotspots):
            if actual_locs[i] not in pred_locs:
                predicted_number = sum_intensity[actual_locs[i][0]][actual_locs[i][1]]*(1/num_points*(self._data.DATE_TIME[end]-self._data.DATE_TIME[start]).total_seconds()*self._time_scale)
                print("Grid: " + str(actual_locs[i]) +", Model: "+ str(predicted_number)+", Real: "+ str(int(tot_events[actual_locs[i][0]][actual_locs[i][1]])))

   
class PointProcessRun(PointProcessTrain):

    def __init__(self, param_location = 'Trained_Params.npz'):

        trained_params = np.load(param_location)
        self._Lam = trained_params['Lam']
        self._theta = trained_params['theta']
        self._w = trained_params['w']
        self._F = trained_params['F']
        self._mu = trained_params['mu']
        self._day = trained_params['day_prob']
        self._hour = trained_params['hour_prob']
        self._Gtimes = pd.DataFrame(trained_params['grid_times'])
        self._LastTime = trained_params['last_time']
        self._K = len(self._w)

        self._time_scale_label = str(trained_params['time_scale'])
        self._time_scaling_lookup = {'days': 1.15741e-5, 'hours': 0.0002777784, '15minutes': 0.001111111, 'minutes': 0.016666704, 'seconds': 1}
        self._time_scale = self._time_scaling_lookup[self._time_scale_label]

        self._xsize = int(trained_params['grid_info'][0])
        self._ysize = int(trained_params['grid_info'][1])
        self._xmin = int(trained_params['grid_info'][2])
        self._xmax = int(trained_params['grid_info'][3])
        self._ymin = int(trained_params['grid_info'][4])
        self._ymax = int(trained_params['grid_info'][5])


    def future_intensity(self, future_time):
        time_delta = (future_time - self._LastTime).total_seconds()*self._time_scale

        future_hour = future_time.hour
        future_day =  future_time.weekday()

        decayed_F_xy = np.zeros(3)

        pred_Lam = np.zeros([self._xsize, self._ysize])
        for x in range(0, self._xsize):
            for y in range(0, self._ysize):
                for k in range(0, self._K):
                    decayed_F_xy[k] = self._F[-1][x][y][k]*np.exp(-self._w[k]*time_delta)
                #pred_Lam[x][y] = self.get_intensity(self._mu[-1][x][y], sum(decayed_F_xy), self._hour[future_hour], self._day[future_day])
                pred_Lam[x][y] = self.get_intensity(self._mu[-1][x][y], sum(decayed_F_xy) / len(decayed_F_xy), self._hour[future_hour], self._day[future_day])
        return pred_Lam

    def test_projection(self, test_points, num_hotspots = 10, time_increment = 900, increment_scale = 'seconds'):
        # test points is a data frame with labels DATE_TIME (datetime format), XCOORD, YCOORD
        # // Attempting to predict over intervals. Currently a work in progress. Not updating parameters as events occur.

        #time_period = int((test_points.DATE_TIME[len(test_points)-1] - test_points.DATE_TIME[0]).total_seconds()*self._time_scale)

        # get everything in seconds to find number of periods to model
        #time_increment = time_increment/self._time_scaling_lookup[increment_scale]   # convert time increment to seconds if it wasn't already. 
        #num_periods = ceil(time_period/time_increment)                               # number of predictions to run at time_increment value each
        #intensity_fraction = time_increment/(1/self._time_scale)                       # intensity will be calculated as #/time_scale. Need it to be #/time_increment

        #print("Intensities are in units of #/" + str(self._time_scale_label) + " Need a fraction of each to correctly add: " +str(intensity_fraction))

        #print("\nPredicting over time of " + str(time_period*self._time_scale) + " " + str(self._time_scale_label) + ". Generating " + str(num_periods) + " intensity prediction(s)")

        #intensity_predictions = np.zeros([time_period, self._xsize, self._ysize])
        #for i in range(0, time_period):
                    #initialize intensity predictions 
        #    future_time = test_points.DATE_TIME[0] + datetime.timedelta(i/self._time_scale)
        #    intensity = self.predict(future_time)   #predict returns #/time_scale. Need the correct fraction of that.
        #    intensity_predictions[i] = intensity
            # if intensity_predictions has been "initialized", start tacking on predictions for later summation
            #if intensity_predictions.any():
            #    intensity_predictions = np.dstack((intensity_predictions, intensity*intensity_fraction))
            # otherwise "initialize" intensity_predictions
            #elif not intensity_predictions.any():
            #    intensity_predictions = np.copy(intensity*intensity_fraction)

        # sum to get prediction over total time of test_points
        #pred_num_events = (sum(intensity_predictions[:,:]))*time_period*self._time_scale
        #print(pred_num_events)
        #print(sum(intensity_predictions[:,:]))

        time_period = (test_points.DATE_TIME[len(test_points)-1] - test_points.DATE_TIME[0]).total_seconds()

        # get everything in seconds to find number of periods to model
        time_increment = time_increment/self._time_scaling_lookup[increment_scale]  # convert time increment to seconds if it wasn't already. 
        num_periods = ceil(time_period/time_increment)                              # number of predictions to run at time_increment value each
        intensity_fraction = time_increment/(1/self._time_scale)                    # intensity will be calculated as #/time_scale. Need it to be #/time_increment

        print("Predicting over time of " + str(time_period*self._time_scale) + " " + str(self._time_scale_label) + ". Generating " + str(num_periods) + " intensity prediction(s)")

        #initialize intensity predictions 
        intensity_predictions = np.zeros([self._xsize, self._ysize])
        for i in range(0, num_periods):
            future_time = test_points.DATE_TIME[0] + datetime.timedelta(seconds=time_increment*i)
            intensity = self.future_intensity(future_time)    
            # if intensity_predictions has been "initialized", start tacking on predictions for later summation
            if intensity_predictions.any():
                intensity_predictions = np.dstack((intensity_predictions, intensity))
            # otherwise "initialize" intensity_predictions
            elif not intensity_predictions.any():
                intensity_predictions = np.copy(intensity)

        # sum to get prediction over total time of test_points
        if num_periods > 1:
            pred_num_events = intensity_predictions.sum(axis=2)*time_period*self._time_scale
        else:
            pred_num_events = intensity_predictions*time_period*self._time_scale

        # find location of num_hotspots predicted hotspots
        c_pred_num_events = np.copy(pred_num_events)
        pred_locs = []
        for i in range(0, num_hotspots):
            indx = unravel_index(c_pred_num_events.argmax(), c_pred_num_events.shape)
            pred_locs.append(indx)
            c_pred_num_events[indx[0]][indx[1]] = 0    

        # get total number of events in each grid 
        tot_events = np.zeros([self._xsize, self._ysize])
        for i in range(0, len(test_points)):
            x, y = self.coord_to_grid(test_points.XCOORD[i], test_points.YCOORD[i])
            tot_events[x][y] = tot_events[x][y] + 1

        # find the location of num_hotspots actual hotspots
        c_tot_events= np.copy(tot_events)
        actual_locs = []
        for i in range(0, num_hotspots):
            indx = unravel_index(c_tot_events.argmax(), c_tot_events.shape)
            actual_locs.append(indx)
            c_tot_events[indx[0]][indx[1]] = 0

        print("\nPredicted hotspots in real top " + str(num_hotspots))
        for i in range(0, num_hotspots):
            if pred_locs[i] in actual_locs:
                x = pred_locs[i][0]
                y = pred_locs[i][1]
                print("Grid: " + str(pred_locs[i]) +", Model: "+ str(pred_num_events[x][y]) + ", Real: " + str(tot_events[x][y]))

        print("\nPredicted hotstpots not in real top " + str(num_hotspots))
        for i in range(0, num_hotspots):
            if pred_locs[i] not in actual_locs:
                x = pred_locs[i][0]
                y = pred_locs[i][1]
                print("Grid: " + str(pred_locs[i]) +", Model: "+ str(pred_num_events[x][y]) + ", Real: " + str(tot_events[x][y]))

        print("\nReal top " +str(num_hotspots) +"  hotspots not predicted")
        for i in range(0, num_hotspots):
            if actual_locs[i] not in pred_locs:
                x = actual_locs[i][0]
                y = actual_locs[i][1]
                print("Grid: " + str(actual_locs[i]) +", Model: "+ str(pred_num_events[x][y]) + ", Real: " + str(tot_events[x][y]))

        return intensity_predictions

    def test_locs_for_wasserstein(self, num_points = 100):
        x_y_lam = np.empty((0,0,0))

        start = self._data_length - num_points
        
        lam = sum(self._Lam[start:,:])/num_points

        for x in range(0, self._xsize):
            for y in range(0, self._ysize):
                xcoord, ycoord = self.grid_to_coord(x, y)
                to_append = xcoord, ycoord, lam[x][y]
                x_y_lam = np.append(x_y_lam, to_append)

        x_y_lam = x_y_lam.reshape ((len(x_y_lam)//3,3))
        return x_y_lam

    def locs_for_wasserstein(self):
        pass
    def num_events_pred(self):
        pass
    def intensity_snapshot(self):
        pass