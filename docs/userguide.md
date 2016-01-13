# Running on CellOS

# Service are available trough the cell gateway
Services are not exposed directly externally

# Scheduling to specific cell subdivisions

Each subdivision's is available through the Mesos `role` attribute:
To set a [Marathon constraint](https://github.com/mesosphere/marathon/blob/master/docs/docs/constraints.md)
to run in the stateless body you can:

    "constraints": [["role", "CLUSTER", "stateless-body"]]


