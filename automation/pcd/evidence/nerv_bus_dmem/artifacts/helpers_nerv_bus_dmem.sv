

	// Sticky history of the most recent dmem-capable bus read.  The wrapper
	// holds the registered read data across stalls, so the history must hold
	// the last dmem read rather than clearing every cycle.
	reg        h_last_bus_valid;
	reg [31:0] h_last_bus_addr;
	reg [31:0] h_last_bus_rdata;
	reg [ 3:0] h_last_bus_rmask;

	always @(posedge clock) begin
		if (reset) begin
			h_last_bus_valid <= 1'b0;
			h_last_bus_addr  <= 32'b0;
			h_last_bus_rdata <= 32'b0;
			h_last_bus_rmask <= 4'b0;
		end else if (rvfi_bus_valid[1] && rvfi_bus_data[1] &&
		             (rvfi_bus_rmask[4 +: 4] != 4'b0000)) begin
			h_last_bus_valid <= 1'b1;
			h_last_bus_addr  <= rvfi_bus_addr[32 +: 32];
			h_last_bus_rdata <= rvfi_bus_rdata[32 +: 32];
			h_last_bus_rmask <= rvfi_bus_rmask[4 +: 4];
		end
	end

	wire h_checked_read = check && rvfi_valid[0] &&
	                      (rvfi_mem_addr == checker_inst.dmem_addr) &&
	                      (rvfi_mem_rmask != 4'b0000);
	wire h_same_last_read = h_checked_read && h_last_bus_valid &&
	                        (h_last_bus_addr == checker_inst.dmem_addr) &&
	                        ((rvfi_mem_rmask & ~h_last_bus_rmask) == 4'b0000);
	wire [31:0] h_byte_mask = {{8{rvfi_mem_rmask[3]}}, {8{rvfi_mem_rmask[2]}},
	                           {8{rvfi_mem_rmask[1]}}, {8{rvfi_mem_rmask[0]}}};

	always @(posedge clock) begin
		if (!reset) begin
			h_checked_read_has_last_bus: assert (!h_checked_read || h_same_last_read);
			h_dmem_eq_last_bus: assert (!h_same_last_read ||
			                            (checker_inst.dmem_shadow === h_last_bus_rdata));
			h_rdata_eq_last_bus: assert (!h_same_last_read ||
			                            ((rvfi_mem_rdata & h_byte_mask) ===
			                             (h_last_bus_rdata & h_byte_mask)));
		end
	end

