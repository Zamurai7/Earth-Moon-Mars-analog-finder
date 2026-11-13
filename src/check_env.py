import sys, pandas, numpy, requests, xarray

print("Python", sys.version.split()[0])

for m in (pandas, numpy, requests, xarray):
    print(m.__name__, m.__version__)

print("Environment OK")