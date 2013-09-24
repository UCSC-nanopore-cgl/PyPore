#!/usr/bin/env python
# Contact: Jacob Schreiber
#          jacobtribe@yahoo.com
# parsers.py 
# 
# This program will read in an abf file using read_abf.py and
# pull out the events, saving them as text files.

from __future__ import division, print_function
import sys
from itertools import tee,izip,chain

import time
import numpy as np
try:
    from PyQt4 import QtGui as Qt
    from PyQt4 import QtCore as Qc
except:
    pass
from core import Segment

try:
    import pyximport
    pyximport.install()
    from PyPore.speedups import FastStatSplit
except:
    pass

#########################################
# EVENT PARSERS
#########################################

class parser( object ):
    def __init__( self ):
        pass
    def parse( self, current ):
        '''
        Take in the full current of a file or event, and return a list of tuples of the format
        ( start, [ current ] ).
        '''
        return [ Segment( current=current, start=0, duration=current.shape[0]/100000 ) ]
    def __repr__( self ):
        rep = self.__class__.__name__ + ": "
        try:
            for key, val in self.gui_attrs.items():
                rep += "{0}:{1}".format(key, value)
        except:
            pass
        return rep 
    def __setattr__( self, key, value ):
        try:
            gui_attrs = getattr( self, "gui_attrs" )
        except AttributeError:
            gui_attrs = {}
        if key != "param_dict":
            gui_attrs[key] = value
            object.__setattr__( self, "gui_attrs", gui_attrs )
        object.__setattr__( self, key, value )
    def GUI( self ):
        grid = Qt.QGridLayout()
        param_dict = {}
        for i, (key, val) in enumerate( self.gui_attrs.items() ):
            param_dict[key] = Qt.QLineEdit()
            param_dict[key].setText( str(val) )
            grid.addWidget( Qt.QLabel(key), i, 0 )
            grid.addWidget( param_dict[key], i, 1 )
        self.param_dict = param_dict
        return grid
    def set_params( self ):
        try:
            for key, lineEdit in self.param_dict.items():
                val = lineEdit.text()
                if '.' in val:
                    setattr( self, key, float( val ) )
                    continue
                for i, letter in enumerate(val):
                    if str(letter) not in '1234567890':
                        setattr( self, key, str( val ) )
                        continue
                    if i == len(val):
                        setattr( self, key, int( val ) )
        except:
            pass


class MemoryParse():
    def __init__( self, starts, ends ):
        self.starts = starts
        self.ends = ends
    def parse( self, current ):
        return [ Segment( current=np.array(current[s:e], copy=True),
                          start=s,
                          duration=(e-s)/100000 ) for s, e in zip(self.starts, self.ends)]

class lambda_event_parser( parser ):
    '''
    A simple rule-based parser which defines events as a sequential series of points which are below a 
    certain threshold, then filtered based on other critereon such as total time or minimum current.
    Rules can be passed in at initiation, or set later, but must be a lambda function takes in a PreEvent
    object and performs some boolean operation. 
    '''
    def __init__( self, threshold=90, rules=None ):
        self.threshold = threshold
        self.rules = rules or [ lambda event: event.duration > 1,
                                lambda event: event.min > -0.5,
                                lambda event: event.max < self.threshold ]
    def _lambda_select( self, events ):
        '''
        From all of the events, filter based on whatever set of rules has been initiated with.
        ''' 
        return [ event for event in events if np.all( [ rule( event ) for rule in self.rules ] ) ]
    
    def parse( self, current ):
        '''
        Perform a large capture of events by creating a boolean mask for when the current is below a threshold,
        then detecting the edges in those masks, and using the edges to partitition the sample. The events are
        then filtered before being returned. 
        '''
        mask = np.where( current < self.threshold, 1, 0 ) # Find where the current is below a threshold, replace with 1's
        mask = np.abs( np.diff( mask ) )                  # Find the edges, marking them with a 1, by derivative
        tics = np.concatenate( ( [0], np.where(mask ==1)[0]+1, [current.shape[0]] ) )
        del mask
        events = [ Segment(current=np.array(current, copy=True), 
                            start=tics[i], 
                            duration=current.shape[0]/100000. ) for i, current in enumerate( np.split( current, tics[1:-1]) ) ]
        return [ event for event in self._lambda_select( events ) ]
    
    def GUI( self ):
        '''
        Override the default GUI for use in the Abada GUI, allowing for customization of the rules and threshol via
        the GUI. 
        '''
        threshDefault, timeDefault = "90", "1"
        maxCurrentDefault, minCurrentDefault = threshDefault, "-0.5" 

        grid = Qt.QGridLayout()
        
        threshLabel = Qt.QLabel( "Maximum Current" )
        threshLabel.setToolTip( "Raw ionic current threshold, which, if dropped below, indicates an event." ) 
        grid.addWidget( threshLabel, 0, 0 )

        self.threshInput = Qt.QLineEdit()
        self.threshInput.setText( threshDefault )
        grid.addWidget( self.threshInput, 0, 2, 1, 1 )

        minCurrentLabel = Qt.QLabel( "Minimum Current (pA):" )
        minCurrentLabel.setToolTip( "This sets a filter requiring all ionic current in an event be above this amount." )
        grid.addWidget( minCurrentLabel, 1, 0 )

        self.minCurrentInput = Qt.QLineEdit()
        self.minCurrentInput.setText( minCurrentDefault )
        grid.addWidget( self.minCurrentInput, 1, 2, 1, 1 )

        timeLabel = Qt.QLabel( "Time:" )
        timeLabel.setToolTip( "This sets a filter requiring all events are of a certain length." )
        grid.addWidget( timeLabel, 3, 0 ) 

        self.timeDirectionInput = Qt.QComboBox()
        self.timeDirectionInput.addItem( ">" )
        self.timeDirectionInput.addItem( "<" )
        grid.addWidget( self.timeDirectionInput, 3, 1 )

        self.timeInput = Qt.QLineEdit()
        self.timeInput.setText( timeDefault )
        grid.addWidget( self.timeInput, 3, 2, 1, 1 )
        return grid

    def set_params( self ):
        '''
        Read in the data from the GUI and use it to customize the rules or threshold of the parser. 
        '''
        self.rules = []
        self.threshold = float( self.threshInput.text() )
        self.rules.append( lambda event: event.max < self.threshold )
        if self.minCurrentInput.text() != '':
            self.rules.append( lambda event: event.min > float( self.minCurrentInput.text() ) )
        if self.timeInput.text() != '':
            if str( self.timeDirectionInput.currentText() ) == '<':
                self.rules.append( lambda event: event.duration < float( self.timeInput.text() ) )
            elif str( self.timeDirectionInput.currentText() ) == '>':
                self.rules.append( lambda event: event.duration > float( self.timeInput.text() ) )
        if self.rules == []:
            self.rules = None

# from itertools documentation
def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = tee(iterable)
    next(b, None)
    return izip(a, b)


class StatSplit( parser ):
    def __init__(self, min_width=1000, max_width=1000000, 
            min_gain_per_sample=0.03, 
                window_width=10000,
                use_log=True,
            splitter="stepwise"):
        """create a segmenter with specified minimum and maximum segment lengths.
        (Default for max_width is 100*min_width)
        min_gain_per_sample is the minimum reduction in variance for a split to be done;
            it is multiplied by window_width to get min_gain.
        If use_log, then minimize the log of varainces, 
            otherwise minimize the variance. 
        splitter is "stepwise", "slanted", or a splitter function.
        """
        self.min_width = max( min_width, 1 ) # Avoid divide by 0
        self.max_width = max_width or 100*min_width
        self.min_gain_per_sample = min_gain_per_sample
        self.window_width = window_width or 10*min_width
        assert self.max_width >= self.min_width 
        assert self.window_width >= 2*self.min_width
        self.use_log = use_log
        self.splitter = splitter
    
    def parse(self,current, start=0, end=-1):
        """segments current[start:end], where current is a numpy array 
        
        returns list of segments:
            [ (start, duration0, left_end, right_end, rms residual)
                  (a1, duration1,  left_end, right_end, rms residual)
                  ...
            ]
        with   min_width <= ai - a_{i-1} = duration_{i-1} <= max_width
        
        With stepwise segmenting, left_end=right_end=mean of segment
        and rms residual = standard deviation of segment.
        """

        # normalize start and end to be normal subscripts
        n = len(current)
        if start < 0: start += n+1
        if end < 0:  end += n+1
        if start > n: start = n
        if end > n: end = n

        if self.splitter=="slanted":
            self.splitter = self._best_split_slanted
        else:
            self.splitter = self._best_split_stepwise

        self.current = current
        self.cum = np.cumsum( current )
        self.cum2 = np.cumsum( np.multiply( current,current ) )
        if self.splitter != self._best_split_stepwise:
            # For covariance computation, need cumulative sum(current*time), 
            # where time is subscript of current array.
            # Needs to be kept in double precision (or higher), since time steps of 1 can
            # be small relative to total array length.
            self.cum_ct = np.cumsum(np.multiply(current, np.linspace(0,end,num=end,endpoint=False)))

        breakpoints =  self._segment_cumulative(start, end)

        # paired is pairs of breakpoints (start,a1), (a1,a2), (a2,a3), ..., (an,end)
        paired = [p for p in pairwise(chain([start],breakpoints,[end])) ]
        assert len(paired)==len(breakpoints)+1
        
        if self.splitter == self._best_split_stepwise:
            # if stepwise splitting is done, left and right endpoints are just the mean
            # and rms residuals are just the standard deviation
            means = [self._mean_c(pair[0],pair[1]) for pair in paired]
            vars = [self._var_c(pair[0],pair[1]) for pair in paired]
            segments = [ Segment( current=current[start:end],
                              start=start,
                              duration=(end-start)/100000 ) for start,end in paired ]
            return segments
            '''
            return [seg for seg in izip(  chain([start],breakpoints),
                          ((e-s) for (s,e) in paired),
                          means,
                          means,
                          (np.sqrt(var) for var in vars )
                       )]
            '''
        lrs = [self._lr(pair[0],pair[1]) for pair in paired]
        lefts = [alpha+beta*s for (alpha,beta,var),(s,e) in izip(lrs,paired)]
        rights = [alpha+beta*e for (alpha,beta,var),(s,e) in izip(lrs,paired)]
        segments = [ Segment( current=current[start:end],
                              start=start,
                              duration=(end-start)/100000 ) for start,end in paired ]
        return segments 
        '''
        return [seg for seg in izip(  chain([start],breakpoints),
                      ((e-s) for (s,e) in paired),
                      lefts,
                      rights,
                      (np.sqrt(var) for alpha,beta,var in lrs)
                   )]
        '''

    def _mean_c(self, start, end):
        """mean value of current for segment start:end
        (uses self.cum a numpy array that is the cumulative sum of
            a current trace (that is, self.cum[i] = sum(self.current[0:i+1]) 
            or self.cum=np.cumsum(self.current) ).
    """
        if start==end: return 0
        if start==0: return self.cum[end-1]/end
        return (self.cum[end-1]-self.cum[start-1])/(end-start)

    def _mean_c2(self, start, end):
        """mean value of current**2 for segment start:end
        (uses self.cum2, a numpy array that is the cumulative sum of
        the square of the current)
    """
        if start==end: return 0
        if start==0: return self.cum2[end-1]/end
        return (self.cum2[end-1]-self.cum2[start-1])/(end-start)

    def _var_c(self, start, end):
        """variance of current for segment start:end
        (uses self.cum2, a numpy array that is the cumulative sum of
        the square of the current)
    """
        if start==end: return 0
        if start==0: return self.cum2[end-1]/end - (self.cum[end-1]/end)**2
        return (self.cum2[end-1]-self.cum2[start-1])/(end-start) \
             - ((self.cum[end-1]-self.cum[start-1])/(end-start))**2

    def _mean_ct(self, start, end):
        """mean value of current[t]*t for segment start:end
        (uses self.cum_ct, a numpy array that is the cumulative sum of
        the current[t]*t
    """
        if start==end: return 0
        if start==0: return self.cum_ct[end-1]/end
        return (self.cum_ct[end-1]-self.cum_ct[start-1])/(end-start)
    
    def _mean_t(self, start,end):
        """mean value of start, ..., end-1"""
        return start+ (end-start-1)/2
    
    def _mean_t2(self,start,end):
        """mean value of start**2, ..., (end-1)**2 """
        return (2*end**2 + end*(2*start-3) + 2*start**2-3*start+1)/6.

    def _lr(self,start,end):
        """does a linear regression on self.current, for segment start:end.
        Returns (alpha, beta,var),
        where current[i] =approx alpha+beta*i
        and var is the mean square residual
        """
        xy_bar = self._mean_ct(start,end)
        y_bar = self._mean_c(start,end)
        x_bar = self._mean_t(start,end)
        x2_bar = self._mean_t2(start,end)
        beta = (xy_bar - x_bar*y_bar)/(x2_bar - x_bar**2)
        alpha = y_bar - beta*x_bar
#        print("DEBUG: lr({},{}) x_bar={} x2_bar={}, y_bar={}, xy_bar={}, alpha={}, beta={}".format(
#           start,end,x_bar, x2_bar, y_bar, xy_bar, alpha, beta))
        y2_bar = self._mean_c2(start,end)
        var = y2_bar - 2*alpha*y_bar- 2*beta*xy_bar +alpha**2 + 2*alpha*beta*x_bar+ beta**2*x2_bar
        return (alpha,beta,var)
    
    def _best_split_stepwise(self, start, end):
        """splits self.cum[start:end]  (0<=start<end<=len(self.current)).
        
        Needs self.cum and self.cum2:
        self.cum is a numpy array that is the cumulative sum of
            a current trace (that is, self.cum[i] = sum(self.current[0:i+1]) 
            or self.cum=np.cumsum(self.current) ).
        self.cum2 is a numpy array that is the cumulative sum of
            the square of the current trace.

        Breakpoint is chosen to maximize the probability of the two segments 
        modeled as two Gaussians.  
        Returns (x,decrease in (log)variance as a result of splitting)
        so that segments are seg1=[start:x], seg2=[x:end]
        with   min_width <= x-start and  min_width <= end-x
        (If no such x, returns None.)
        
        Note decrease in log variance is proportional to 
            log p1(seg1) + log p2(seg2) - log pall(seg1+seg2))
        so that this is a maximum-likelihood estimator of splitting point
        """
#   print("DEBUG: splitting", start,"..",end, "min=",self.min_width,file=sys.stderr)
        if end-start< 2*self.min_width:  
#           print("DEBUG: too short", start,"..",end, file=sys.stderr)
            return None
        var_summed = (end-start)*(self._var_c(start,end) if not self.use_log 
                else np.log(self._var_c(start,end)))
        max_gain=self.min_gain_per_sample*self.window_width
        x=None
        for i in xrange(start+self.min_width,end+1-self.min_width):
            low_var_summed = (i-start)*( self._var_c(start,i) if not self.use_log
                    else np.log(self._var_c(start,i)))
            high_var_summed = (end-i)*( self._var_c(i,end) if not self.use_log
                    else np.log(self._var_c(i,end)))
            gain =  var_summed - (low_var_summed+high_var_summed)
            if gain > max_gain:
                max_gain= gain
                x=i
        if x is None: 
#           print("DEBUG: nothing found", start,"..",end, file=sys.stderr)
            return None
        #print("# DEBUG: splitting at x=", x, "gain/sample=", max_gain/self.window_width, file=sys.stderr)
        
        return (x,max_gain)
    
    def _best_split_slanted(self, start, end):
        """
        splits self.cum[start:end]  (0<=start<end<=len(self.current)).
        
        Needs self.cum, self.cum2, and self.cum_ct:
        self.cum is a numpy array that is the cumulative sum of
            a current trace (that is, self.cum[i] = sum(self.current[0:i+1]) 
            or self.cum=np.cumsum(self.current) ).
        self.cum2 is a numpy array that is the cumulative sum of
            the square of the current trace.
        self.cum_ct is a numpy array that is the cumulative sum of current[i]*i
        
        Breakpoint is chosen to maximize the probability of the two segments 
        modeled as two straight-line segments plus Gaussian noise.
        
        Returns (x, (log)variance decrease as a result of splitting)
        so that segments are seg1=[start:x], seg2=[x:end]
        with   min_width <= x-start and  min_width <= end-x
        (If no such x, returns None.)
        """

#   print("DEBUG: splitting", start,"..",end, "min=",self.min_width,file=sys.stderr)
        if end-start< 2*self.min_width:  
#           print("DEBUG: too short", start,"..",end, file=sys.stderr)
            return None
        var_summed = (end-start)*( self._lr(start,end)[2] if not self.use_log
            else log(self._lr(start,end)[2]))
        max_gain=self.min_gain_per_sample*self.window_width
        x=None
        for i in xrange(start+self.min_width,end+1-self.min_width):
            low_var_summed = (i-start)*(self._lr(start,i)[2] if not self.use_log
                else log(self._lr(start,i)[2]))
            high_var_summed = (end-i)*(self._lr(i,end)[2] if not self.use_log
                else log(self._lr(i,end)[2]))
            gain =  var_summed - (low_var_summed+high_var_summed)
            print(gain)
            if gain > max_gain:
                max_gain= gain
                x=i
        if x is None: 
#           print("DEBUG: nothing found", start,"..",end, file=sys.stderr)
            return None
        #print("# DEBUG: splitting at x=", x, "gain/sample=", max_gain/self.window_width, file=sys.stderr)
        
        return (x,max_gain)

    # PROBLEM: this recursive splitting can have O(n^2) behavior,
    # if each split only removes min_width from one end, because
    # the self.splitter routines take time proportional to the length of the segment being split.
    # Keeping window_width small helps, since behavior is 
    #  O( window_width/min_width *(end-start) 
    def _segment_cumulative(self, start, end):
        """segments cumulative sum of current and current**2 (in self.cum and self.cum2)
        returns [a1, a2, ...,  an]
        so that segments are [start:a1], [a1:a2], ... [an:end]
        with   min_width <= ai - a_{i-1} <= max_width
        (a0=start a_{n+1}=end)
        """
        
        # scan in overlapping windows to find a spliting point
        split_pair = None
        pseudostart = start
        for pseudostart in xrange(start, end-2*self.min_width, self.window_width//2 ):
            if pseudostart> start+ self.max_width:
            # scanned a long way with no splits, add a fake one at max_width
                split_at = min(start+self.max_width, end-self.min_width)
                #print("# DEBUG: adding fake split at ",split_at, "after", start, file=sys.stderr)
                return [split_at] + self._segment_cumulative(split_at,end) 

            # look for a splitting point
            pseudoend =  min(end,pseudostart+self.window_width)
            split_pair = self.splitter(pseudostart,pseudoend)
            if split_pair is not None: break

        if split_pair is None:
            if end-start <=self.max_width:
                # we've split as finely as we can, subdivide only if end-start>max_width 
                return []
            split_at = min(start+self.max_width, end-self.min_width)
            #print("# DEBUG: adding late fake split at ",split_at, "after", start, file=sys.stderr)
        else:
            split_at,gain = split_pair
        
        # splitting point found, recursively try each subpart
        return  self._segment_cumulative(start,split_at) \
            + [split_at] \
            + self._segment_cumulative(split_at,end)

class SpeedyStatSplit(parser):
    def __init__( self, min_width=1000, max_width=1000000, window_width=10000, min_gain_per_sample=0.03 ):
        self.min_width = min_width
        self.max_width = max_width
        self.min_gain_per_sample = min_gain_per_sample
        self.window_width = window_width

    def parse( self, current ):
        parser = FastStatSplit( self.min_width, self.max_width, self.window_width, self.min_gain_per_sample )
        return parser.parse( current )

    def GUI( self ):
        grid = Qt.QGridLayout()
        grid.addWidget( Qt.QLabel( "Minimum Width (samples): "), 0, 0, 1, 3)
        grid.addWidget( Qt.QLabel( "Maximum Width (samples): " ), 1, 0, 1, 3 )
        grid.addWidget( Qt.QLabel( "Window Width (samples): " ), 2, 0, 1, 3 )
        grid.addWidget( Qt.QLabel( "Minimum Gain / Sample: " ), 3, 0, 1, 3 )
        
        self.minWidth = Qt.QLineEdit()
        self.minWidth.setText('1000')
        self.maxWidth = Qt.QLineEdit()
        self.maxWidth.setText('1000000')
        self.windowWidth = Qt.QLineEdit('10000')
        self.windowWidth.setText('10000')
        self.minGain = Qt.QLineEdit()
        self.minGain.setText('0.05')

        grid.addWidget( self.minWidth, 0, 3 )
        grid.addWidget( self.maxWidth, 1, 3 )
        grid.addWidget( self.windowWidth, 2, 3 )
        grid.addWidget( self.minGain, 3, 3 )
        return grid

    def set_params( self ):
        try:
            self.min_width = int(self.minWidth.text())
            self.max_width = int(self.maxWidth.text())
            self.window_width = int(self.windowWidth.text())
            self.min_gain_per_sample = float(self.minGain.text())
        except:
            print ("herp")
            pass

#########################################
# STATE PARSERS 
#########################################

class snakebase_parser( parser ):
    '''
    A simple parser based on dividing when the peak-to-peak amplitude of a wave exceeds a certain threshold.
    '''
    def __init__( self, threshold=1.5, merger_thresh = 2.0 ):
        self.threshold = threshold
        self.merger_thresh = merger_thresh
    def parse( self, current ):
        # Take the derivative of the current first
        diff = np.abs( np.diff( current ) )
        # Find the places where the derivative is low
        tics = np.concatenate( ( [0], np.where( diff < 1e-3 )[0], [ diff.shape[0] ] ) )
        # For pieces between these tics, make each point the cumulative sum of that piece and put it together piecewise
        cumsum = np.concatenate( ( [ np.cumsum( diff[ tics[i] : tics[i+1] ] ) for i in xrange( tics.shape[0]-1 ) ] ) )
        # Find the edges where the cumulative sum passes a threshold
        split_points = np.where( np.abs( np.diff( np.where( cumsum > self.threshold, 1, 0 ) ) ) == 1 )[0] + 1
        # Merge states which don't pass a given t-score threshold
        tics = merger( threshold = self.merger_thresh ).merge( split_points, current )
        # Return segments which do pass the threshold
        return [ Segment( current = current[ tics[i]: tics[i+1] ], start = tics[i] ) for i in xrange( 1, tics.shape[0] - 1, 2 ) ]
    def GUI( self ):
        threshDefault = "1.5"
        mergerThreshDefault = "2.0"

        grid = Qt.QGridLayout()
        grid.setVerticalSpacing(0)
        grid.addWidget( Qt.QLabel( "Threshold" ), 0, 0 )
        self.threshInput = Qt.QLineEdit()
        self.threshInput.setToolTip("Peak to peak amplitude threshold, which if gone above, indicates a state transition.")
        self.threshInput.setText( threshDefault )

        grid.addWidget( Qt.QLabel( "Merger Threshold" ), 1, 0 )
        self.mergerThreshInput = Qt.QLineEdit()
        self.mergerThreshInput.setToolTip( "T-score that adjacent states must be away to prevent merger." )
        self.mergerThreshInput.setText( mergerThreshDefault ) 

        grid.addWidget( self.threshInput, 0, 1 )
        grid.addWidget( self.mergerThreshInput, 1, 1 )
        return grid
    def set_params( self ):
        self.threshold = float( self.threshInput.text() )
        self.merger_thresh = float( self.mergerThreshInput.text() )

class novakker_parser( parser ):
    '''
    A reimplimentation by Jacob Schreiber of Adam Novak's original parser, to a more vectorized form.
    '''
    def __init__( self, low_thresh=1, high_thresh=2, merger_thresh=2.0 ):
        self.low_thresh = low_thresh
        self.high_thresh = high_thresh
        self.merger_thresh = merger_thresh
    def parse( self, current ):
        deriv = np.abs( np.diff( current ) )
        # Find the edges of where a series of points have a derivative greater than a threshold, notated as a 'block'
        tics = np.concatenate( ( [ 0 ], np.where( np.abs( np.diff( np.where( deriv > self.low_thresh, 1, 0 ) ) ) == 1 )[0] + 1 , [ deriv.shape[0] ] ) ) 
        # Split points will be the indices of points where the derivative passes a certain threshold and is the maximum of a 'block'
        split_points = []
        for i in xrange( 0, len(tics)-1, 2 ): # For all pairs of edges for a block..
            segment = deriv[ tics[i]:tics[i+1] ] # Save all derivatives in that block to a segment
            if np.argmax( segment ) > self.high_thresh: # If the maximum derivative in that block is above a threshold..
                split_points = np.concatenate( ( split_points, [ tics[i], tics[i+1] ] ) ) # Save the edges of the segment 
                # Now you have the edges of all transitions saved, and so the states are the current between these transitions
        tics = merger( threshold = self.merger_thresh ).merge( split_points, current )
        tics = np.concatenate( ( [0], split_points, [ current.shape[0] ] ) )
        return [ Segment( current = current[ tics[i]: tics[i+1] ], start = tics[i] ) for i in xrange( 0, tics.shape[0] - 1, 2 ) ]

    def GUI( self ):
        lowThreshDefault = "1e-2"
        highThreshDefault = "1e-1"
        mergerThreshDefault = "1.0"

        grid = Qt.QGridLayout()
        grid.addWidget( Qt.QLabel( "Low-pass Threshold: " ), 0, 0 )
        grid.addWidget( Qt.QLabel( "High-pass Threshold: " ), 1, 0 )
        grid.addWidget( Qt.QLabel( "Merger Threshold" ), 2, 0 )

        self.lowThreshInput = Qt.QLineEdit()
        self.lowThreshInput.setText( lowThreshDefault )
        self.lowThreshInput.setToolTip( "The lower threshold, of which one maximum is found." )
        self.highThreshInput = Qt.QLineEdit()
        self.highThreshInput.setText( highThreshDefault )
        self.highThreshInput.setToolTip( "The higher threshold, of which the maximum must be abov." )
        self.mergerThreshInput = Qt.QLineEdit()
        self.mergerThreshInput.setText( mergerThreshDefault )
        self.mergerThreshInput.setToolTip( "T-score that adjacent states must be away to prevent merger." )

        grid.addWidget( self.lowThreshInput, 0, 1 )
        grid.addWidget( self.highThreshInput, 1, 1 )
        grid.addWidget( self.mergerThreshInput, 2, 1 )
        return grid
    def set_params( self ):
        self.low_thresh = float( self.lowThreshInput.text() )
        self.high_thresh = float( self.highThreshInput.text() )
        self.merger_thresh = float( self.mergerThreshInput.text() )

class merger( object ):
    def __init__( self, threshold ):
        self.threshold = threshold
    def merge( self, tics, current ):
        badtics = []
        for i in xrange( 3, len( tics ) - 3, 2 ):
            last_state = current[ tics[i-2] : tics[i-1] ]
            next_state = current[ tics[i+2] : tics[i+3] ]
            curr_state = current[ tics[i]   : tics[i+1] ]
            u = np.abs( np.mean( last_state ) - np.mean( curr_state ) ) / np.sqrt( np.std( last_state ) * np.std( curr_state ) )
            v = np.abs( np.mean( next_state ) - np.mean( curr_state ) ) / np.sqrt( np.std( next_state ) * np.std( curr_state ) )
            if v <= self.threshold:
                badtics = np.concatenate( ( badtics, [i+1, i+2] ) )
            if u <= self.threshold:
                badtics = np.concatenate( ( badtics, [i-1, i] ) )
        tics = np.delete( tics, badtics )
        return tics 
