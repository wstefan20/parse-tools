# -*- coding: utf-8 -*-
"""
Written by:     Shawn Herrington, Paul Klappa, Cody Smith, Demetri Reed
Date:           09/12/2019
Purpose:        Combine data recorded at disparate rates into a master file
Purpose:        Developed on faux data and then modified to work specifically
                with PX4 data which has been converted using the pyulog utility
                (specically the ulog2csv module)
Notes:          Modified to remove gui interaction so that script can be called
                from higher level parser script, also converted to function
                for easy calling from parent script
Notes:          Fastest sampling time is calculated automatically, it is tested
                working but if conditions change and it stops working it would 
                be easier to just type in max freq by hand than to troubleshoot
                or modify, parts of the code containing the min freq nonsense
                have been noted
Notes:          Currently the output is saved to a directory which is created
                in order to avoid having the "results.csv" script read as input
                data if this script is run in a directory where it has already
                been run previously, this could be improved in future versions
                by specifically ignoring csv files that are output by this
                script when we build the list of csv files to crawl
Notes:          Currently only tested in Python 2.7; although, the print
                functions at the end which are just for convenience may be the
                only part that needs modification to run on Python 3
Notes:          When you run the script select the directory of interest (in
                most cases this will be Test_##\FlightData\).  The script will
                read in all constituent csv files (stored in FlightData) then
                process the timestamp and do some important operations on the
                df before resampling to the minimum frequency and writing the
                contents to a file called 'results.csv' in a directory called
                'combined' which will be created if it does not already exist
Notes:          The script does not need to be copied and pasted into the
                directory of interest, that is handled by the askdirectory() 
                function
Changelog:
09/12/2019  Shawn Herrington
            Fixed some bozo mistakes on the index renaming on the resampled
            array.  Was resuing the time_properformat var from the big_df var
            but that var was being ffill-ed by the resample command and giving
            time values that made no sense, found a method to extract the
            datetime index as an int and all is working now
09/24/2019  Simeon Karnes
            The function in lines 62-63 have been flagged as false to avoid the
            delay in time to recreate the big csv file just to make plots
            again. To re-enable combining into the large csv file, set line 62
            to True.
09/26/2019  Shawn Herrington
            Moved enable/disable flag to the top of the file for ease of access
            Changed column names in the big csv to account for columns with
            duplicate names.  Previously duplicate column names were
            overwritten.  Now the constitutent csv file name is added to each
            variable so that there can be no duplicate names.
            For example "q[0]" is now named "vehicle_attitude_0_q[0]", this
            will cause dataframe slicing on column names to break but this
            change was necessary to fix a bug.  Future releases should account
            for the full column name (or use partial matching were appropriate)
"""

import os
import pandas as pd
import numpy as np
import make_plots

# if files have already been resampled, set this to True to save time
need_to_make_big_csv = True

def combine_and_resample_px4_nogui(input_path,file_suffix=''):
    
    # fix this for 250Hz rate since the auto calculator is causing issues
    min_sampletime = .004
    freq_arg = int(min_sampletime*10**6)
    freq_type = 'U'    
    
    os.chdir(input_path)
    
    if need_to_make_big_csv:
       
        # get list of filenames in directory ending with csv
        list_of_filenames = [f for f in os.listdir('.') if f.endswith('.csv')]
        
        # create empty list so we can append to it
        list_of_df = []
        
        exclude_list = ['position_setpoint_triplet_0','sensor_selection_0','telemetry_status_0','vehicle_status_flags_0','mission_result_0']
        
        # iterate through the csv in the current directory, create a df for each
        # filename, put the df into a list of other df
        for current_filename in list_of_filenames:
            
            if not any(excluded_name in current_filename for excluded_name in exclude_list):
            
                # create match string, this will be used to remove the test name from the
                # filename when creating df columns
                # duplicate columns were being deleted so constituent csv titles were
                # added to column headers but they now have "Test_XX" added to them, and
                # since the number of digits varies the string has to be removed more
                # carefully than by slicing
                _, match_string = os.path.split(os.path.dirname(input_path))
                           
                # this is the important read, read in the data we care about, the index is
                # stored in column 0, the header is stored in row 0, pandas will name columns
                # automatically for us using the header row
                df = pd.read_csv(current_filename, index_col=0, header=0)
                
                # create list of df columns
                list_of_column_names = list(df.columns)
                list_of_new_column_names = []
                            
                for column_name in list_of_column_names:
                    
                    # append the filename (minus extension onto each var in the resampled file)
                    new_column_name = current_filename[:-4] + '_' + column_name
                                    
                    # replace the text "Test_XX" with blanks
                    new_column_name = new_column_name.replace(match_string+'_','')
                    
                    # build the new name list
                    list_of_new_column_names.append(new_column_name)
                
                # create dicitonary from key = old names, values = new names
                rename_dictionary = dict(zip(list_of_column_names,list_of_new_column_names))
                
                # invoke rename method using created dict to rename columns intelligently
                df.rename(columns = rename_dictionary,inplace=True)
                     
                # store the current df (from a single csv) into the big list of dfs
                list_of_df.append(df)
           
        # create the big df by using the concat method called on a list of small df
        big_df = pd.concat(list_of_df, axis=0, ignore_index=False, sort=False)
        
        # sort on the timestamp column, otherwise the small df are stuck together end
        #-to-end which isn't what we want
        big_df = big_df.sort_values(by='timestamp')
        
        # for px4 some data files start with 0 for timestamp, we don't want this, so
        # we will just discard these rows for now
        big_df = big_df.drop(0, errors="ignore")
        
        # offset time to zero just because we can
        big_df.index = big_df.index - big_df.index[0]
        
        # fill the missing spaces, use ffill to move the most recent valid observation
        # forward
        big_df = big_df.fillna(method='ffill')
        
        # fill the remaining na with 0, these only happen at the beginning where we
        # previously did not have any observations to pass forward
        big_df = big_df.fillna(0)
        
        # get rid of duplicate rows, not sure this iis needed but keeping just in case
        # UPDATE:  definitely needed, first line gets rid of duplicate time entries
        big_df = big_df[~big_df.index.duplicated()]
        # this one gets rid of duplicated output data, not sure this is required
        big_df = big_df.drop_duplicates()
        
        # create a time delta column with the proper format, note the use of 10**6 to 
        # modify time stamp since timestamp for px4 data is in microseconds, 'S' means
        # that this function is expected time formated ins seconds so the easiest way
        # to fix it is just to convert the number to seconds before passing it
        big_df['time_properformat'] = pd.to_timedelta(big_df.index/10.0**6,'S')
        
        # switch the index of the big_df to proper time delta column
        big_df.index = pd.to_datetime(big_df.time_properformat.astype('int64'))
               
        # create the resampled  df
        resampled_df = big_df.asfreq(str(freq_arg)+freq_type,method='ffill')
        
        # get rid of the annoying time index, switch back to delta time in seconds
        resampled_df.index = resampled_df.index.values.astype(np.uint64)/1000
        
        # get rid of the unused column before we send it to csv
        resampled_df = resampled_df.drop(columns=['time_properformat'])
        
        # check if folder exists and create if needed, this avoid the script trying
        # to read it's own results.csv as one of the constituent files if we run
        # this script on a directory where it has been run at least once previously
        if not os.path.exists('combined'):
            os.mkdir('combined')
        
        # write the result, we want to write the index column, we want to label the index
        # column, feel free to change the name
        resampled_df.to_csv(path_or_buf=os.path.join('combined',file_suffix+'_combined.csv'),index=True,index_label='cpu_time')
        
    print('Resampling complete.')
    print('Minimum sample time is:\t%f s\nThe corresponding frequency is:\t%f Hz\nOutput saved to:  %s' % (min_sampletime,1/min_sampletime,os.path.join('combined',file_suffix+'_combined.csv')))

    make_plots.make_plots(os.path.join('combined',file_suffix+'_combined.csv'))



