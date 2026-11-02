return {
	resources = {
		nwqsim = "nwqsim",
		["ornl-iqm-20q"] = "iqm-ornl-20q",
		["ornl-shim-20q"] = "shim-ornl-20q",
		["ibm-156-nh"] = "shim-ibm-156-nh",
		["aws-ionq-aria-1"] = "shim-aws-qpm",
		["aws-rigetti-ankaa"] = "shim-aws-qpm",
		["fake-iqm-20q"] = "fake-iqm",
		["backline-local"] = "backline-local",
		["ibm-fake-lagos"] = "shim-ibm-fake-lagos",
		["pasqal-emu-free"] = "shim-pasqal-emu-free",
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
				["backline-local"] = true,
				["ibm-fake-lagos"] = true,
				["pasqal-emu-free"] = true,
			},
		},
	},
}
