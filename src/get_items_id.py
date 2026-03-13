import requests
import pandas as pd
import requests.auth
from datetime import datetime, timezone

def event_is_change(event):
    if "fields" not in event:
        return None
    if "System.State" not in event["fields"]:
        return None
    return (event["fields"]["System.State"], event["fields"]["System.ChangedDate"])


def get_log_per_id(organization, project, id, pat):
    
    api = f"https://dev.azure.com/{organization}/{project}/_apis/wit/workItems/{id}/updates?api-version=7.1-preview.3"
    print(f"Extrayendo datos de: {api}")
    response = requests.get(api, auth=requests.auth.HTTPBasicAuth('', pat))
    if response.status_code == 200:
        responseData = response.json()["value"]
        dataFilterAplied = [r for r in responseData]
        
        projectName = "Desarrollo" if dataFilterAplied[0]["fields"]["System.AreaPath"] == "Promigas" else "Soporte" 
        rows = []
        prevChangeDate = None
        for r in dataFilterAplied:
            change_info = event_is_change(r)
            if change_info:    
                try:
                    prevState = change_info[0]['oldValue']
                except KeyError:
                    prevState = None
                state = change_info[0]['newValue']
                changeDate = change_info[1]['newValue']
                workItemId = r["id"]

                try:
                    prevStateID = prevState
                except:
                    prevStateID = None
                try:
                    stateID = state
                except:
                    stateID = None

                
                
                row = [id, workItemId, prevStateID, stateID, prevChangeDate, changeDate, r["rev"]]
                prevChangeDate = changeDate
                rows.append(row)
        rows.append([id, workItemId, stateID, 'last', changeDate, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-4] + "Z",  r["rev"]])
        return (rows, workItemId)
    else:
        print(f"Error con {id}: {response.status_code}")
        return ([], id)

def apply_fecha_corte(df, fecha_corte=None):
    if df.empty:
        return df

    if fecha_corte is None:
        df["cumple"] = None
        return df

    fecha_corte_dt = pd.to_datetime(fecha_corte, utc=True)

    df["prevChangeDate"] = df["prevChangeDate"].fillna("2025-01-01T05:00:00Z")
    df["prevChangeDate"] = pd.to_datetime(df["prevChangeDate"], format='ISO8601', utc=True).dt.tz_localize(None)
    df["changeDate"] = pd.to_datetime(df["changeDate"], format='ISO8601', utc=True).dt.tz_localize(None)
    fecha_corte_naive = fecha_corte_dt.tz_localize(None) if fecha_corte_dt.tzinfo is None else fecha_corte_dt.replace(tzinfo=None)
    
    print(df[["workItemId", "prevChangeDate", "changeDate", "state"]].head(20))
    print("fecha_corte_naive:", fecha_corte_naive)
    
    df["cumple"] = (
        (fecha_corte_naive > df["prevChangeDate"]) &
        (fecha_corte_naive < df["changeDate"])
    )

    return df

def create_dataframe(idList, organization, project, pat, fecha_corte=None):
    rows = []
    for i in idList:
        rows_response, _ = get_log_per_id(organization=organization, project=project, id=i, pat=pat)
        rows += rows_response

    df = pd.DataFrame(rows, columns=["workItemId", "idLog", "prevState", "state", "prevChangeDate", "changeDate", "rev"])

    # estado actual: la fila con state == 'last' guarda en prevState el estado más reciente
    df_actual = (
        df[df["state"] == "last"][["workItemId", "prevState"]]
        .rename(columns={"prevState": "estado_actual"})
    )

    # estado en la fecha de corte
    df_for_corte = df[df["state"] != "last"].copy()  
    df_for_corte = apply_fecha_corte(df_for_corte, fecha_corte)

    if fecha_corte is not None:
        df_estado_corte = (
            df_for_corte[df_for_corte["cumple"] == True][["workItemId", "prevState"]]
            .rename(columns={"prevState": "estado_fecha_corte"})
        )
    else:
        df_estado_corte = pd.DataFrame(columns=["workItemId", "estado_fecha_corte"])

    # join y columna final
    df_resultado = df_actual.merge(df_estado_corte, on="workItemId", how="left")
    df_resultado["estado_final"] = df_resultado["estado_fecha_corte"].fillna(df_resultado["estado_actual"])

    return df_resultado