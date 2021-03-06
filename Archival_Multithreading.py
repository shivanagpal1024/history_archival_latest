import logging
import sys
import pytz
import configparser as cp
import pymysql
import csv
import ibm_db_dbi as dbi
from tqdm import tqdm
import sys
import os
from datetime import datetime
from datetime import date
import os.path
from os import path
from ftplib import FTP
import os
from multiprocessing import Process
import shutil
IST = pytz.timezone('Asia/Kolkata') 


global hprtnid
global procprd

del_cnt = 0
counter = 1
cnt = 0
gb_size = 1024 * 1024 * 1024 * 2.0  # 2GB
size = 0
division_counter = 0
threshold = 10000
cnt_written=0

cnt=0
log = logging.getLogger('root')  # return a logger which is he root logger of the hierarchy
FORMAT = "[%(levelname)s: %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(format=FORMAT)
log.setLevel(logging.DEBUG)
DB2_config = {}

DB2_config = {}
mysql_config = {}

def get_sys_argument():
    global table
    global runtype
    log.info("Getting System Arguments to Derive the Archival Prcoess")
    if len(sys.argv) == 2:
        runtype= sys.argv[1]
        if runtype.upper()=='M':
            table='INT_MBR'
        elif runtype.upper()=='C':
            table="INT_MBR_COV"
        else:
            log.error("No valid Argument passed to drive the Program=%s ", (sys.argv))
            sys.exit(-1)

        log.info(f"Getting Started with Archival Process for {table} table")
    else:
        log.error("No valid Argument passed to drive the Program=%s ", (sys.argv))
        sys.exit(-1)

def create_output_folder():
    global d1
    global tab1
    global input_dir_path
    global output_dir_path
    global reg_qual
    today = date.today()
    d1 = today.strftime("%Y%m")
    input_dir_path = f'/history_archival_files/input_{table}'
    if os.path.isdir(input_dir_path):
        shutil.rmtree(input_dir_path)
    os.mkdir(input_dir_path)
    check_for_configuration()
    reg_qual = DB2_config['region'.strip()][-3:]
    tab1=table.replace("_","")
    if tab1=='INTMBRCOV':
        tab1='INTMBRCV'
    output_dir_path = f'/history_archival_files/output_{table}_{d1}'
    if os.path.isdir(output_dir_path):
        pass
    else:
        os.mkdir(output_dir_path)

def create_input_files():
    log.info("Creating input files Name for reading,corresponding to Mainframe Files ")
    if reg_qual=='DBP':
        fir_qual='B6744PRD'
    else:
        fir_qual='F6744DEV'
    for i in range(1,26):
        folders=[f'U{runtype}{i}']
        for folder in folders:
            folder_path=f'{output_dir_path}/{folder}'
            succ_path=f'{folder_path}/H_{table}_{folder}.SUCCESS'
            csv_path=f'{folder_path}/H_{table}_{folder}.csv'
            if os.path.isdir(folder_path):
                if os.path.exists(succ_path):
                    continue
                else:
                    if os.path.exists(csv_path):
                        os.remove(csv_path)
                    filnm = f'{fir_qual}.{reg_qual}.U{runtype}{i}.{tab1}.ARC.UNLD.P{d1}'
                    with open('{file_nm}.txt'.format(file_nm=os.path.join(input_dir_path, '{}'.format(filnm))),
                              'w+') as ifile:
                        writer = csv.writer(ifile)
            else:
                filnm = f'{fir_qual}.{reg_qual}.U{runtype}{i}.{tab1}.ARC.UNLD.P{d1}'
                with open('{file_nm}.txt'.format(file_nm=os.path.join(input_dir_path, '{}'.format(filnm))),
                          'w+') as ifile:
                    writer = csv.writer(ifile)
    log.info("Input files created")

def check_for_configuration():
    log.info("Reading configuration file")
    config = cp.ConfigParser()
    config.read("DB2.properties")
    error_list = []
    for key, value in config['db2'].items():
        if value is None or value.strip() == '':  # Checking if the property file is empty
            error_list.append(f'{key} \"{value}\" not found or incorrect\n')
        else:
            DB2_config[key] = value  # Storing each value for DB connection in list
    for key, value in config['mysql'].items():
        if value is None or value.strip() == '':
            error_list.append(f'{key} \"{value}\" not found or incorrect\n')
        else:
            mysql_config[key] = value
    if len(error_list) != 0:
        log.error("something went wrong while reading configuration=%s", error_list)
        sys.exit(-1)
    log.info("configuration file read successfully config_size=%s", len(DB2_config))

def db2_connection():
    global conn
    global region
    log.info("Connecting to DB2 database")
    dbase = DB2_config['database'.strip()]
    region = DB2_config['region'.strip()]
    hstnm = DB2_config['hostname'.strip()]
    port = DB2_config['port'.strip()]
    protocol = DB2_config['protocol'.strip()]
    usrid = DB2_config['uid'.strip()]
    pswd = DB2_config['pwd'.strip()]
    try:
        # Attempt To Establish A Connection To The Database Specified
        conn = dbi.connect(f"DATABASE={dbase};HOSTNAME={hstnm};PORT={port};PROTOCOL={protocol};UID={usrid};PWD={pswd};",
                           "", "")
        # If A Db2 Database Connection Could Not Be Established, Display An Error Message And Exit
    except Exception as e:
        log.error(
            "ERROR:Unable to connect to the DB2 Connection host=%s, username=%s, password=%s, database=%s, message=%s",
            hstnm, usrid, pswd, dbase, str(e))
        sys.exit(-1)
    log.info("DB2 connection created")

def ftp_connection():
    global ftp_conn
    log.info("Creating FTP Connection")
    hst = DB2_config['host'.strip()]
    usrid = DB2_config['uid'.strip()]
    pswd = DB2_config['pwd'.strip()]
    try:
        # Attemp to Establish the FTP Connection with Mainframe
        ftp_conn=FTP()
        ftp_conn.connect('{}'.format(hst))
        ftp_conn.login(user='{}'.format(usrid), passwd='{}'.format(pswd))
    except Exception as e:
        log.error(
            "ERROR:Something went wrong while creating FTP connection host=%s, username=%s, password=%s message=%s",
            hst,usrid,pswd, str(e))
    log.info("FTP connection created")

def h_partn_xref(region):
    '''
    It Will get the all the PROC_PRD and PARTN_ID from the table and store it in respective list
    :param region:
    :return: list of PARTN_ID and PROC_PRD
    '''
    global hprtnid
    global procprd
    sql = "SELECT  PROC_PRD,H_PARTN_ID FROM {}.H_PARTN_XREF ORDER BY PROC_PRD DESC WITH UR;".format(region)
    cursor = conn.cursor()
    cursor.execute(sql)
    results = cursor.fetchall()
    hprtnid = []
    procprd = []
    count = 0
    try:
        for row in results:
            count += 1
            procprd.append(row[0])
            hprtnid.append(row[1])
        return hprtnid, procprd
    except Exception as err:
        log.error("Error:Unable to Fetch the result from H_PARTN_XREF table: {0}".format(err))
        conn.close()
        conn.rollback()

def write_archive_file(line):
    global cnt
    cnt+=1
    list=[]
    new_list=[]
    rows_lst = []
    # Separating each field read from the Mainframe file and delimited by Separator('|') and storing in a list
    for item in line.split("|"):
        list.append(item)
    # For each field stored in a list type casting is done
    for item in list:
        item=item.strip()
        item = item[1:-1] if item[0] == ',' and item[-1] == ',' else item
        try:
            #  Try to type cast the field in int
            item = int(item)
            # if it can't be type cast to int
        except Exception as e:
            try:
                # an attempt to type cast to to datetime object
                item = datetime.strptime(item, '%Y-%m-%d-%H.%M.%S.%f')
                # if it is not cast to datetime object
            except Exception as e:
                # type cast to string
                item = str(item)
        finally:
            # Adding the type cast field to the new_list
            new_list.append(item)
    # Adding Partn_id prior to the enitre record
    updt_tm = new_list[index]
    yearmo = updt_tm.strftime("%Y%m")
    if yearmo in list_proc_prd:
        loc = list_proc_prd.index(yearmo)
        himpartnid = list_hprtn_id[loc]
    elif yearmo < list_proc_prd[-1]:
        himpartnid = list_hprtn_id[-1]
    row1 = new_list[:-1]
    row1.insert(0, himpartnid)
    # remove trailing spaces in the field if any
    lst = [elt.strip() if type(elt) is str else elt for elt in row1]
    rows_lst.append(lst)
    file_path_size = os.path.join(dir_path, f'H_{table}_{csvfilnm}')
    with open('{file_path}.csv'.format(file_path=os.path.join(dir_path, f'H_{table}_{csvfilnm}')), 'a', newline='\n') as hintmbr:
        writer = csv.writer(hintmbr)
        writer.writerows(rows_lst)
    size = os.path.getsize(f'{file_path_size}.csv')
    if cnt >= 2840000:
        cnt=0
        in_gb_size = size / (1024 * 1024 * 1024)
        log.info(f'{in_gb_size} GB of data written to H_{table}_{csvfilnm}')


def read_file(filename):
    global list_hprtn_id
    global list_proc_prd
    global read_lines
    global mfilnm
    global d1
    global table
    global index
    global dir_path
    global csvfilnm
    global cnt_written
    check_for_configuration()
    db2_connection()
    list_hprtn_id, list_proc_prd = h_partn_xref(region)
    ftp_connection()
    today = date.today()
    d1 = today.strftime("%Y%m")
    if sys.argv[1]=='M':
        table='INT_MBR'
        index=26
    elif sys.argv[1]=='C':
        table = 'INT_MBR_COV'
        index=33
    else:
        log.error("No valid Argument passed to drive the Program=%s ", (sys.argv))
        sys.exit(-1)
    mfilnm = filename[:-4]
    csvfilnm = mfilnm.split('.')[2]
    dir_path = f'/history_archival_files/output_{table}_{d1}/{csvfilnm}'
    if os.path.isdir(dir_path):
        pass
    else:
        os.mkdir(dir_path)
    log.info(f'Reading {mfilnm} file from Mainframe')
    cnt_written = 0
    ftp_conn.retrlines('RETR ' + "'{}'".format(mfilnm), write_archive_file )
    success_process(csvfilnm)
    load_into_mysql(csvfilnm)
    wrapping_up()

def success_process(csvfilnm):
    log.info(f'csv created successfully for H_{table}_{csvfilnm}')
    with open('{file_path}.SUCCESS'.format(file_path=os.path.join(dir_path, f'H_{table}_{csvfilnm}')), 'w+') as success:
        writer = csv.writer(success)

def load_into_mysql(csvfilnm):
    loadcsvfile = f'{dir_path}/H_{table}_{csvfilnm}.csv'
    log.info(f'Connecting to Mysql Database to load the {loadcsvfile}')
    ms_hst = mysql_config['mysql_host']
    ms_usr = mysql_config['mysql_user']
    ms_pswrd = mysql_config['mysql_password']
    ms_database = mysql_config['mysql_database']
    try:
        mysqldb = pymysql.connect(host=ms_hst, user=ms_usr, password=ms_pswrd, database=ms_database,autocommit=True, local_infile=1)
        log.info("mysql connection created")
        cursor = mysqldb.cursor()
        query = (
            f"LOAD DATA LOCAL INFILE %s INTO TABLE ecap01.h_{table} FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\\r\\n';")
        cursor.execute(query, (loadcsvfile,))
        mysqldb.commit()
        mysqldb.close()
        log.info(f'File {loadcsvfile} loaded to MYSQL database successfully')
    except Exception as e:
        log.error(
            "something went wrong while creating connection host=%s, username=%s, password=%s, database=%s, message=%s",
            ms_hst, ms_usr, ms_pswrd, ms_database, str(e))
        sys.exit(-1)


def wrapping_up():
    if len(sys.argv) == 2:
        runtype= sys.argv[1]
        if runtype=='M':
            table='INT_MBR'
        elif runtype=='C':
            table="INT_MBR_COV"
    input_dir_path = f'/history_archival_files/input_{table}'
    log.info(f'Deleting H_{table}_{csvfilnm} file from the {dir_path} folder and corresponding input file from {input_dir_path} folder')
    if os.path.exists(f'{dir_path}/H_{table}_{csvfilnm}.csv'):
        os.remove(f'{dir_path}/H_{table}_{csvfilnm}.csv')
    if os.path.exists(f'{input_dir_path}/{mfilnm}.txt'):
        os.remove(f'{input_dir_path}/{mfilnm}.txt')
    log.info(f'Files H_{table}_{csvfilnm} deleted successfully')

if __name__ == '__main__':
    dateTimeObj1 = datetime.now(IST)
    timestampStr = dateTimeObj1.strftime("%d-%b-%Y (%H:%M:%S.%f)")
    log.info(f"Start Time:{timestampStr}")
    print("Start Time:",timestampStr)
    get_sys_argument()
    create_output_folder()
    create_input_files()
    processes = []
    i=1
    while (os.listdir(f'{input_dir_path}/') and i<3):
        i=i+1
        for filename in os.listdir(f'{input_dir_path}/'):
            if filename[-3:] == 'txt':
                p = Process(target=read_file, args=[filename])
                p.start()
                processes.append(p)
                print(processes)
        for p in processes:
            p.join()
    dateTimeObj2 = datetime.now(IST)
    timestampend = dateTimeObj2.strftime("%d-%b-%Y (%H:%M:%S.%f)")
    log.info(f"End Time:{timestampend}")
    print("End Time:", timestampend)
