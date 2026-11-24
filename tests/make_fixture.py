"""Builds a synthetic parquet shaped like Overture places. Names are fake on purpose."""
import duckdb, pathlib
out = pathlib.Path(__file__).parent / "fixture.parquet"
rows = [
 ("t1","Test Cafe One","coffee_shop",0.9,"open",37.2296,-80.4139,"100 Test St","Blacksburg","https://example.com","+15405550101"),
 ("t2","Test Barber Two","barber",0.8,"open",37.2301,-80.4150,"102 Test St","Blacksburg",None,None),
 ("t3","Test Bar Three","bar",0.8,"open",37.2310,-80.4160,"104 Test St","Blacksburg",None,None),
 ("t4","Test Auto Parts Four","auto_parts_store",0.7,"open",37.1300,-80.4090,"1 Sample Rd","Christiansburg",None,None),
 ("t5","Test Closed Five","restaurant",0.9,"permanently_closed",37.2290,-80.4100,"5 Gone Ln","Blacksburg",None,None),
 ("t6","Test Low Confidence Six","restaurant",0.2,"open",37.2290,-80.4100,"6 Maybe Ln","Blacksburg",None,None),
 ("t7","Test Outside Bbox Seven","restaurant",0.9,"open",38.5,-79.0,"7 Far Rd","Elsewhere",None,None),
 ("t8","Test Vet Eight","veterinarian",0.9,"open",37.2250,-80.4200,"8 Paw Ct","Blacksburg",None,None),
 ("t9","Test Mystery Nine","zzz_unknown",0.9,"open",37.2260,-80.4210,"9 Odd Way","Blacksburg",None,None),
]
con = duckdb.connect()
con.execute("""CREATE TABLE p AS SELECT * FROM (VALUES """ + ",".join(
 f"""('{i}', {{'primary':'{n}'}}, '{c}', {{'primary':'{c}','hierarchy':['{c}']}}, {conf}, '{st}',
     {{'xmin':{lng}::DOUBLE,'xmax':{lng}::DOUBLE,'ymin':{lat}::DOUBLE,'ymax':{lat}::DOUBLE}},
     [{{'freeform':'{a}','locality':'{t}','region':'VA'}}],
     {('[' + repr(w) + ']') if w else 'NULL'}::VARCHAR[], {('[' + repr(ph) + ']') if ph else 'NULL'}::VARCHAR[])"""
 for i,n,c,conf,st,lat,lng,a,t,w,ph in rows) +
 ") AS t(id,names,basic_category,taxonomy,confidence,operating_status,bbox,addresses,websites,phones)")
con.execute(f"COPY p TO '{out}' (FORMAT parquet)")
print("wrote", out)
