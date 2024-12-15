import streamlit as st
import re
import datetime as dt
import pandas as pd
import sqlite3
import math

st.set_page_config(layout="wide")

def calc_distance(lat1, lon1, lat2, lon2):

    R = 6378137  # Earth's radius in meters

    # Convert latitude and longitude from degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    distance = R * c
    return distance

def calc_bearing(lat1, lon1, lat2, lon2):

    # Convert latitude and longitude from degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    dlon = lon2 - lon1

    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)

    initial_bearing = math.atan2(x, y)
    
    # Convert bearing from radians to degrees and normalize to 0-360
    bearing = (math.degrees(initial_bearing) + 360) % 360
    return bearing

def calc_angle(a,b):
    if a < b:
        diff = b - a
    else:
        diff = a - b

    if diff > 180:
        diff = 360 - diff

    return diff

def calc_acceleration(v0, v1, t):
    return round( (v1 - v0) * 1000 / 3600 / 9.80665 , 2)

#文字列を時刻、緯度経度にパースする
def parse_gps_string(gps_string):
    pattern = r'(\d{2}:\d{2}:\d{2})\s[NS](\d+)゜(\d+)\'([\d.]+)"\s[EW](\d+)゜(\d+)\'([\d.]+)"'                                                   
    match = re.match(pattern, gps_string)

    try:
        # 時刻の抽出
        time = match.group(1)
        time = dt.datetime.strptime(time,'%H:%M:%S').time()
    except AttributeError:
        raise ValueError(f'GPS データとして解釈できませんでした : {gps_string}')
  
    # 緯度の抽出と度(10進法)への変換
    lat_deg = int(match.group(2))
    lat_min = int(match.group(3))
    lat_sec = float(match.group(4))
    latitude = (lat_deg + lat_min / 60 + lat_sec / 3600)
    
    # 経度の抽出と度(10進法)への変換
    lon_deg = int(match.group(5))
    lon_min = int(match.group(6))
    lon_sec = float(match.group(7))
    longitude = (lon_deg + lon_min / 60 + lon_sec / 3600)

    return time, latitude, longitude

#文字列を格納した配列をパースして配列で返す
def parse_gps_strings(gps_strings):
    temp = []
    for gps_string in gps_strings:
        try:
            time, lat, lon = parse_gps_string(gps_string)
        except:
            pass
        else:
            temp.append([time, lat, lon])
    return temp

def gps_array_to_db(gps_array,table_name='gps'):
    con = sqlite3.connect(':memory:')
    df = pd.DataFrame(gps_array, columns=['time','lat','lon'])
    df.to_sql(table_name,con=con,index=False)
    return con

def check_duplicate(con):
    sql = '''
    select time, a.* from (select * from (select lat, lon, count(*) as count from gps group by lat, lon) where count > 1) as a join gps as b on a.lat = b.lat and a.lon = b.lon;
    '''
    return pd.read_sql(sql=sql, con=con)

def elapsed_sec(time):
    return int(time.hour * 3600 + time.minute * 60 + time.second)

def calc_movement(lines):
    t0, lat0, lon0, x0 = None, None, None, None
    temp = []
    
    for n,x in enumerate(lines):
        t1, lat1, lon1 = x
        if t0 != None:
            diff = elapsed_sec(t1) - elapsed_sec(t0)
            dist = calc_distance(lat0,lon0,lat1,lon1)
            bearing = calc_bearing(lat0,lon0,lat1,lon1)
            x0.append(diff)
            x0.append(dist)
            x0.append((dist / diff) * 3.6 if diff != 0 else None )
            x0.append(bearing)
            temp.append(x0)
        else:
            x9 = x.copy()
            x9.append(None)
            x9.append(None)
            x9.append(None)
            x9.append(None)
            temp.append(x9)
            
        t0 = t1
        lat0 = lat1
        lon0 = lon1
        x0 = x.copy()

    return pd.DataFrame(temp, columns=['time','lat','lon','経過時間','距離','時速','方向'])


def calc_movement_change(df):
    laps, dist, speed, bearing = None, None, None, None
    for n, x in df.iterrows():
    
        if speed != None:
            g = calc_acceleration(speed,x.時速,x.経過時間)
            angle = calc_angle(bearing, x.方向)
            df.at[n,'重力加速度'] = g
            df.at[n,'方向変化'] = angle
    
        speed = x.時速
        bearing = x.方向
    return df

def check_movement(df):

    df['description'] = ''
    df['error'] = 0
    df['color'] = '#00000077'
    df['size'] = 20

    for n,x in df.iterrows():

        if x.重力加速度 > 2 or x.重力加速度 < -2:
            df.at[n,'error'] += 1
            df.at[n,'color'] = '#7F1184AA' #紫色
            df.at[n,'size'] += 10
            df.at[n,'description'] += '速度変化大, '

        if x.方向変化 > 90:
            df.at[n,'error'] += 1
            df.at[n,'color'] = '#F58220AA' #オレンジ
            df.at[n,'size'] += 10
            df.at[n,'description'] += '方向変化大, '

        if x.距離 == 0:
            df.at[n,'error'] += 1
            df.at[n,'color'] = '#F30100AA' #赤色
            df.at[n,'size'] += 5
            df.at[n,'description'] += '移動なし, '

        if x.経過時間 > 1:
            df.at[n,'error'] += 1
            df.at[n,'color'] = '#F30100AA' #赤色
            df.at[n,'size'] += 20
            df.at[n,'description'] += 'データ欠損, '

    return df


st.header('GPSチェッカー',divider=True)
text = st.text_area('GPSファイルをメモ帳で開いて内容を↓に貼り付けてください')
lines = text.splitlines()
gps = parse_gps_strings(lines)
if len(gps) == 0:
    st.warning('有効なデータがありません。正しいGPSログを貼り付けてください。')
    st.stop()

con = gps_array_to_db(gps)
df_dup_checked = check_duplicate(con)
df = calc_movement(gps)
df = calc_movement_change(df)
df = check_movement(df)

df_error = df[df['error'] > 0]

# st.subheader('重複チェック',divider=True)
# st.text('位置が重複するポイントがあった場合に出力されます。')
# st.dataframe(df)

# df2 = calc_movement(gps)
# df3 = df2[df2['経過時間'] > 1]

# st.subheader('欠損チェック',divider=True)
# st.text('データに欠損があった場合（時間が不連続）に出力されます。')
# st.dataframe(df3)

st.subheader('エラーの疑い',divider=True)
st.dataframe(df_error.iloc[:,[0,1,2,3,4,5,6,7,8,9,10]], use_container_width=True)
st.subheader('地図',divider=True)
st.map(df,latitude='lat', longitude='lon', color='color', size='size')
st.markdown('''
:violet[●紫色]：速度変化が大。  
:orange[●オレンジ]：方向変化が大              
:red[●赤]：重複ポイント・欠損ポイント
''')
