# Cell reliability

All core cell services are highly available.
However, as a cell is typically deployed in a single AZ, its availability will be at most that of the AZ. 
Depending on the availability requirements for your application, you may consider deploying services across more than one cell.

# Multi AZ Availability

## Multi AZ Cells?

While we could deploy a cell cross AZ and try to benefit from the potentially increased availability 
at the entire cell level, there would be some things we'd need to consider.

**Cons:**

* Quorums require `N / 2 + 1`, so we'd need to be in an odd number of AZs for ZK to survive properly.
* Cross AZ traffic costs money. Arbitrary cross-AZ traffic may be prohibitively expensive.
** Although this may seem cheap, I've seen a bill with a huge cross AZ item caused by running jobs 
across AZs. 
* Cross AZ traffic may not be reliable. This can translate in a complete slowdown of 
any quorum operation as data would need to be replicated on N / 2 + 1 servers. 
* Quorum operations affect Mesos scheduling, HBase region assignment, etc. 
* Other cross AZ traffic like HDFS could also be slowed down. 
This could be potentially fixed with a custom HDFS block placement policy, HBase region placement policy etc.

A simpler design would be to consider a cell in one AZ (and be an equivalent failure domain)  
and increase availability by deploying workloads across multiple cells.

I.e. we keep the cell as a failure domain and just deploy failover services across cells  
and solve the problem at the higher level.

E.g. HBase and Kafka replication could solve the problem both cross AZ as well as cross region.  
HDFS doesn't have a cross cluster replication, although some tooling exists. 

Cell to cell traffic could be solved both at VPC level (through VPC peering or equivalent)   
and at a service level (api-gateway based load balancer).

For arbitrary cold file storage HDFS may not be cost efficient for storage bound cells.  
Instead, these could be stored in the available object store (e.g. S3) 
FileSystem API makes this transparent, through a simple configuration of s3://bucket.

This is not a replacement for hot storage in HDFS, as the S3 backend is much slower, but it is a possible solution.

Besides cost considerations using an available object store like S3 may provide a simpler 
solution for files availability. 
**Note** that CellOS provisions an S3 bucket for each cell already. 

# Cross Region Availability

Cross region availability is by and large similar, however S3 bandwidth across buckets 
in different regions should be considered
