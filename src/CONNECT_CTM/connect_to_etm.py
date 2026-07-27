from .ctm_client import CTMClient
from .constants import SCENARIO_YEARS, ALL_SCENARIOS
import json

# CTM_session_ids = {
#     ("Elektrificatie", "2030"): "SE-89f8540c58b9fc6a",
#     ("Elektrificatie", "2035"): "SE-19d830420db7f899",
#     ("Elektrificatie", "2040"): "SE-da08be308c9a4556",
#     ("Elektrificatie", "2050"): "SE-c5332b6227c5c4c2",

#     ("Midden", "2030"): "SE-8a908306100118e4",
#     ("Midden", "2035"): "SE-9803ea651d4b0624",
#     ("Midden", "2040"): "SE-1c5a78163215a601",
#     ("Midden", "2050"): "SE-48093e0f349a59a4",

#     ("Groen gas", "2030"): "SE-cc671dd37573c664",
#     ("Groen gas", "2035"): "SE-ce856785a8d4a023",
#     ("Groen gas", "2040"): "SE-52168f1bb3ea0e92",
#     ("Groen gas", "2050"): "SE-1d9b959dd009ac23",

#     ("VT", "2030"): "SE-cde60c34e93c8291",
#     ("VT", "2035"): "SE-3ede563331a92306",
#     ("VT", "2040"): "SE-1992a16c210555c9",
#     ("VT", "2050"): "SE-7cffed6e5c0c57f2",

#     ("Waterstof", "2030"): "SE-241292136d54292b",
#     ("Waterstof", "2035"): "SE-dc41aa7fc36b5131",
#     ("Waterstof", "2040"): "SE-bc28ad038daa5694",
#     ("Waterstof", "2050"): "SE-e2c3305ca0f9f95e",
# }


# THESE ARE THE NEW SESSIONS

CTM_session_ids = {
    ("Elektrificatie", "2030"): "SE-ad8f11f8e02c59cc",
    ("Elektrificatie", "2035"): "SE-30569a0bed67948d",
    ("Elektrificatie", "2040"): "SE-1baebb319fba5ba6",
    ("Elektrificatie", "2050"): "SE-5f2344f47588521f",

    ("Midden", "2030"): "SE-ffa162d5308c29bf",
    ("Midden", "2035"): "SE-7562a845fc791712",
    ("Midden", "2040"): "SE-752d12b7d4c050bb",
    ("Midden", "2050"): "SE-543d8ec4a87bfab7",

    ("Groen gas", "2030"): "SE-827492f3dc78c59d",
    ("Groen gas", "2035"): "SE-27308488ea42f3e7",
    ("Groen gas", "2040"): "SE-ae83f46207d384cc",
    ("Groen gas", "2050"): "SE-f36b215869cf13c7",

    ("VT", "2030"): "SE-16fa5e5a751cdb47",
    ("VT", "2035"): "SE-4630c0537179025e",
    ("VT", "2040"): "SE-818f593b41ac9c87",
    ("VT", "2050"): "SE-2fed91be8ca55119",

    ("Waterstof", "2030"): "SE-70fc26a187609ef2",
    ("Waterstof", "2035"): "SE-95758114a80f1d93",
    ("Waterstof", "2040"): "SE-3eaae100a90058e9",
    ("Waterstof", "2050"): "SE-ef1092beb13732e1",
}

ETM_session_ids = {
    ("Midden", "2030"): "1444392",
    ("Midden", "2035"): "1444394",
    ("Midden", "2040"): "1444396",
    ("Midden", "2045"): "1444398",
    ("Midden", "2050"): "1444400",

    ("VT", "2030"): "1450978",
    ("VT", "2035"): "1450970",
    ("VT", "2040"): "1450972",
    ("VT", "2045"): "1450974",
    ("VT", "2050"): "1450976",

    ("Elektrificatie", "2030"): "1450934",
    ("Elektrificatie", "2035"): "1450936",
    ("Elektrificatie", "2040"): "1450938",
    ("Elektrificatie", "2045"): "1450943",
    ("Elektrificatie", "2050"): "1450945",

    ("Groen gas", "2030"): "1450947",
    ("Groen gas", "2035"): "1450949",
    ("Groen gas", "2040"): "1450951",
    ("Groen gas", "2045"): "1450953",
    ("Groen gas", "2050"): "1450955",

    ("Waterstof", "2030"): "1450957",
    ("Waterstof", "2035"): "1450959",
    ("Waterstof", "2040"): "1450961",
    ("Waterstof", "2045"): "1450963",
    ("Waterstof", "2050"): "1450965",
}

etm_test_session = '1463394'

token = 'etm_eyJraWQiOiJkODI5ZTk3YTU4ZDhhOTQyYjg3NGI5ZjNiZWI3ZDJlNGY0MTA5ZjIzNWE0Y2NhMDkzYmU5MzFiMzY1NTlkNGI2IiwiYWxnIjoiUlMyNTYifQ.eyJpc3MiOiJodHRwczovL215LmVuZXJneXRyYW5zaXRpb25tb2RlbC5jb20iLCJpYXQiOjE3ODI1MDQ2ODQsImF1ZCI6Imh0dHBzOi8vZW5naW5lLmVuZXJneXRyYW5zaXRpb25tb2RlbC5jb20gaHR0cHM6Ly8yMDI1LTAxLmVuZ2luZS5lbmVyZ3l0cmFuc2l0aW9ubW9kZWwuY29tIiwic2NvcGVzIjoib3BlbmlkIHB1YmxpYyBzY2VuYXJpb3M6cmVhZCBzY2VuYXJpb3M6d3JpdGUiLCJqdGkiOiI2YmZjOWZkOS1iMTA4LTQzZDgtYTcxMi0yOGZmZDVmMjkyNzkiLCJzdWIiOjE2NzQwLCJ1c2VyIjp7ImlkIjoxNjc0MCwiYWRtaW4iOmZhbHNlLCJlbWFpbCI6InJ1eGFuZHJhLnNpbWlvbml1YzIyQGdtYWlsLmNvbSIsIm5hbWUiOiJSdXhhbmRyYSAifSwiZXhwIjoxNzkwMjgwNjg0fQ.R5HchFBEO-jB-yhCZHrDvA2duO5487uX8uErARnm0sFVWzLyBoLJxdce9Ikm7g7qrsickGnHAiT92jWf7dDBq-4nzXq84680siD3tVeE3MN5T5QihTxEtLtzg_XOTxGsyalwNWOJpfMSQKYw8_Db4pqBDfGphYA6JoipiBco-r0lnk1a0puKKhZzERsXf6taEnQsuW0v0cJpyp9yhzXuC8gYhzKtkX4PlIY96rT3KiGMnti78FkXcbfCqiNdeLFG6cTS7dz0AB4s-SxwDRlvlXL7nse-QNxb1mfvUMAR83vcs8EWww9isKG97m6QBgh3GNMP9BCYDTis0GnD9B30uQ'
emmanuel_token = 'etm_eyJraWQiOiJkODI5ZTk3YTU4ZDhhOTQyYjg3NGI5ZjNiZWI3ZDJlNGY0MTA5ZjIzNWE0Y2NhMDkzYmU5MzFiMzY1NTlkNGI2IiwiYWxnIjoiUlMyNTYifQ.eyJpc3MiOiJodHRwczovL215LmVuZXJneXRyYW5zaXRpb25tb2RlbC5jb20iLCJpYXQiOjE3ODI1NTU5ODksImF1ZCI6Imh0dHBzOi8vZW5naW5lLmVuZXJneXRyYW5zaXRpb25tb2RlbC5jb20gaHR0cHM6Ly8yMDI1LTAxLmVuZ2luZS5lbmVyZ3l0cmFuc2l0aW9ubW9kZWwuY29tIiwic2NvcGVzIjoib3BlbmlkIHB1YmxpYyBzY2VuYXJpb3M6cmVhZCBzY2VuYXJpb3M6d3JpdGUiLCJqdGkiOiIyZjY0NGJkMy1kMDI3LTRlNWEtYTQ1YS1mOGZkYTQzMzU1ZjciLCJzdWIiOjExNjYxLCJ1c2VyIjp7ImlkIjoxMTY2MSwiYWRtaW4iOmZhbHNlLCJlbWFpbCI6Im5ibmxzY2VuYXJpb3MudGFza2ZvcmNlc0BnbWFpbC5jb20iLCJuYW1lIjoiTkJOTCBTY2VuYXJpb3MgKFRhc2tmb3JjZXMpIn0sImV4cCI6MTgxNDA5MTk4OX0.Z2CDH5-5A76h239qY_tLXnXdAugKjzLdJoAvmRXiO8tUhm5BhyYxtvqKqj4oDMw40QV5G8DsVdczrUp-bJfzGLfft4gcbVCR3BTvRtOaazp_1C88-dwSF4diT0WbNilvHe4_7IH32E7QWjlsMd5EIN07i9bHD6lmozI6n7G7FEmSIddO1mKLcr4H16nnl8BE8sz-jXGZ9nqSon31h2ouxyWea3BlRN6Qp5ElMjoLAHnriQ1oMIuLZusCyGgc3xesLfpHKr5PUZhrqZmW2SCnw7m2p105CvB0ucKVwJi2AfKhDXwwul6VAZS5lBaSp7sj7EZQ-Ggc7vgPjI-5Xt8O2w'

ctm_session_id = "SE-89f8540c58b9fc6a"
scenario = 'Elektrificatie'
year = '2030'



def push_ctm_scenario_to_etm(ctm_session:str, etm_session:str, etm_token:str):
    try:
        ctm = CTMClient(use_beta=True)
        ctm.load_session(session_id=ctm_session)
    except:
        print('Err loading the CTM session')

    # Try coupling immediately (empty session)
    try:
        etm_result = ctm.couple_etm(
            auth_token=etm_token,
            etm_session_id=etm_session
        )
        print('Pushed CTM session to ETM')
        return etm_result
    except Exception as e: 
        print(f'Err pushing to ETM: {e}')  


save_path = "/home/307920@ontw.alfa.local/projects/epn-ma-master/src/CONNECT_CTM/logs/etm_push_22_07"
failed = []

for scenario in ALL_SCENARIOS:
    for year in SCENARIO_YEARS:
        ctm_session = CTM_session_ids[(scenario, year)]
        etm_session = ETM_session_ids[(scenario, year)]
        # if ctm_session in ['SE-f36b215869cf13c7']:
        try:
            # etm_result = push_ctm_scenario_to_etm(ctm_session_id, etm_test_session, token)
            print(f'Loading and pushing {scenario}, {year}: {ctm_session}')
            etm_result = push_ctm_scenario_to_etm(ctm_session, etm_session, emmanuel_token)

            # print(f'Success for {scenario}, {year}')

            inputs_file = f'{save_path}/etmresult_{scenario}_{year}.json'
            with open(inputs_file, "w") as f:
                json.dump(etm_result, f, indent=4)
            print()
        except Exception as e:
            failed.append((scenario, year, ctm_session))
            print(f'Error for {scenario}, {year}: {e}')


print('D O N E')

# scenario = 'Elektrificatie'
# year = '2035'

# ctm_session = CTM_session_ids[(scenario, year)]
# etm_session = ETM_session_ids[(scenario, year)]
# try:
#     # etm_result = push_ctm_scenario_to_etm(ctm_session_id, etm_test_session, token)
#     etm_result = push_ctm_scenario_to_etm(ctm_session, etm_session, emmanuel_token)

#     print(f'Success for {scenario}, {year}')

#     inputs_file = f'{save_path}/etmresult_{scenario}_{year}_test.json'
#     with open(inputs_file, "w") as f:
#             json.dump(etm_result, f, indent=4)
#     print()
# except Exception as e:
#     print(f'Error for {scenario}, {year}: {e}')





# ctm = CTMClient(use_beta=True)
# ctm.load_session(ctm_session_id)

# outputs = ctm.get_all_outputs()

# etm_test_scenario = '36582'
# etm_test_session = '1463394'

# # # Couple each session to ETM
# # etm_session = ctm.couple_etm(
# #     etm_scenario_id=etm_test_scenario,
# #     auth_token=token,
# # )

# # print(f"CTM {scenario}/{year}: {ctm_session_id}")
# # print(f"  -> Coupled to ETM: {etm_session}")

# ctm = CTMClient(use_beta=True)
# # session_id = ctm.create_clean_sheet_session()
# ctm.load_session(session_id=ctm_session_id)

# # Try coupling immediately (empty session)
# try:
#     etm_result = ctm.couple_etm(
#         # etm_scenario_id=36582,
#         auth_token=token,
#         etm_session_id=etm_test_session
#     )
#     print(etm_result)
# except: 
#     print('oh no')  
# # ctm.delete_session()

# print('x')
