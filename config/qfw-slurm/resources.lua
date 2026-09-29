return {
	resources = {
		nwqsim = "nwqsim",
		["ornl-iqm-20q"] = "iqm-ornl-20q",
		["ornl-shim-20q"] = "shim-ornl-20q",
		["ibm-156-nh"] = "shim-ibm-156-nh",
		["fake-iqm-20q"] = "fake-iqm",
	},
	partitions = {
		normal = {
			allowed = {
				nwqsim = true,
				["ornl-iqm-20q"] = true,
				["ornl-shim-20q"] = true,
				["ibm-156-nh"] = true,
				["fake-iqm-20q"] = true,
			},
		},
	},
}
