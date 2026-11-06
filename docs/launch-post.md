# Draft: launch post for helyxit.com (not published)

**Title:** An AWS waste scanner you can read in an afternoon

Most cost tools want broad access to your account and send data to someone else's SaaS.
I am a Lead SRE, and I would not hand that over either, so I built the scanner I wanted.

**aws-waste-hunter** is open source (Apache-2.0) and read-only by construction:
- Every AWS call is `Describe*`, `List*` or `Get*`, enforced in code, in tests, and in the IAM
  policy you attach. It was verified against a real policy-only role: writes are denied.
- It runs on your machine or CI. No agent, no SaaS, no telemetry (a test fails if the source
  imports a network module).
- It speaks dollars: live AWS prices, per-finding monthly cost and savings.
- Metric-based checks (idle NAT gateways, idle load balancers) have a hard CloudWatch cost cap.
- Tested on a real account: it caught a false-positive bug that mocks could not.

What it will not do is the part that saves the most: architecture, data transfer, Savings
Plans and Reserved Instances, EKS right-sizing. That is what Helyx reviews are for, with a
guaranteed 15% savings. [Book a call](https://helyxit.com).

Links: repo, sample report, threat model.
