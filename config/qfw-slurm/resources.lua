return {
	resources = {
		nwqsim = "nwqsim",
		["ornl-iqm-20q"] = "iqm-ornl-20q",
		["ornl-shim-20q"] = "shim-ornl-20q",
		["ibm-156-nh"] = "shim-ibm-156-nh",
		["aws-ionq-aria-1"] = "shim-aws-qpm",
		["aws-rigetti-ankaa"] = "shim-aws-qpm",
		["fake-iqm-20q"] = "fake-iqm",
	},
	partitions = {
		normal = {
			allowed = {
				nwqsim = true,
				["ornl-iqm-20q"] = true,
				["ornl-shim-20q"] = true,
				["ibm-156-nh"] = true,
				["aws-ionq-aria-1"] = true,
				["aws-rigetti-ankaa"] = true,
				["fake-iqm-20q"] = true,
			},
		},
	},
}
