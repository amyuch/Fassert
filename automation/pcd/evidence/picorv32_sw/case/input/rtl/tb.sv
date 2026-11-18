`default_nettype none
`include "defines.sv"

// free input variables, can take any value each cycle as long as the `assume` are satisfied
module testbench (
	input check,
	input clock, reset
);
	`RVFI_WIRES
	`RVFI_BUS_WIRES

	`RISCV_FORMAL_CHECKER checker_inst (
		.clock  (clock),
		.reset  (reset),
		.check   (check),
		`RVFI_CONN
		`RVFI_BUS_CONN
	);

	// Ignore rvfi_order loopback, otherwise the check might be invalid.
	reg rvfi_order_loopback;
	always @(posedge clock) begin
		if (reset) begin
			rvfi_order_loopback <= 0;
		end else if (rvfi_valid && rvfi_order == {64{1'b1}}) begin
			rvfi_order_loopback <= 1;
		end
	end
	always_comb assume (!(rvfi_order_loopback && check));

	rvfi_wrapper wrapper (
		.clock (clock),
		.reset (reset),
		`RVFI_CONN
		`RVFI_BUS_CONN
	);

/// Helper Assertion Begin

	// --- CIll SW store-path helper set ---
	wire h_is_sw = (wrapper.uut.dbg_insn_opcode[6:0] == 7'b0100011) &&
	               (wrapper.uut.dbg_insn_opcode[14:12] == 3'b010);
	wire h_rvfi_sw = (rvfi_insn[6:0] == 7'b0100011) &&
	                 (rvfi_insn[14:12] == 3'b010);
	wire h_sw_mem_phase = h_is_sw &&
	                      (wrapper.uut.cpu_state == 8'b00000010) &&
	                      wrapper.uut.mem_do_wdata;
	wire [31:0] h_dbg_imm = {{20{wrapper.uut.dbg_insn_opcode[31]}},
	                         wrapper.uut.dbg_insn_opcode[31:25],
	                         wrapper.uut.dbg_insn_opcode[11:7]};

	reg        h_st_seen;
	reg [31:0] h_st_addr;
	reg [31:0] h_st_insn;
	reg [31:0] h_st_rs1;
	reg [31:0] h_st_rs2;
	wire [31:0] h_st_imm = {{20{h_st_insn[31]}},
	                        h_st_insn[31:25],
	                        h_st_insn[11:7]};

	always @(posedge clock) begin
		if (reset) begin
			h_st_seen <= 1'b0;
			h_st_addr <= 32'd0;
			h_st_insn <= 32'd0;
			h_st_rs1  <= 32'd0;
			h_st_rs2  <= 32'd0;
		end else begin
			if (rvfi_valid)
				h_st_seen <= 1'b0;
			if (h_sw_mem_phase && wrapper.uut.dbg_mem_valid &&
			    wrapper.uut.dbg_mem_ready && !wrapper.uut.dbg_mem_instr &&
			    (wrapper.uut.dbg_mem_wstrb != 4'd0)) begin
				h_st_seen <= 1'b1;
				h_st_addr <= wrapper.uut.dbg_mem_addr;
				h_st_insn <= wrapper.uut.dbg_insn_opcode;
				h_st_rs1  <= wrapper.uut.dbg_rs1val;
				h_st_rs2  <= wrapper.uut.dbg_rs2val;
			end
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			h_rvfi_insn_eq: assert (rvfi_insn == $past(wrapper.uut.dbg_insn_opcode));
			h_rvfi_pc_rdata_eq: assert (rvfi_pc_rdata == $past(wrapper.uut.dbg_insn_addr));
			h_rvfi_valid_eq: assert (rvfi_valid == $past((!reset) && (wrapper.uut.launch_next_insn || wrapper.uut.trap) && wrapper.uut.dbg_valid_insn));
			h_rvfi_mem_addr_eq: assert (rvfi_mem_addr == $past(
				wrapper.uut.dbg_irq_call ? rvfi_mem_addr :
				(wrapper.uut.dbg_mem_instr ? 32'd0 :
				 ((wrapper.uut.dbg_mem_valid && wrapper.uut.dbg_mem_ready) ?
					wrapper.uut.dbg_mem_addr : rvfi_mem_addr))));

			h_sw_stmem_addr: assert (!(h_sw_mem_phase && wrapper.uut.mem_valid) ||
				wrapper.uut.dbg_mem_addr == {wrapper.uut.reg_op1[31:2], 2'b00});
			h_sw_capture_addr: assert (!(h_sw_mem_phase && wrapper.uut.dbg_mem_valid &&
				wrapper.uut.dbg_mem_ready && !wrapper.uut.dbg_mem_instr) ||
				wrapper.uut.dbg_mem_addr ==
					((wrapper.uut.dbg_rs1val + h_dbg_imm) & ~32'd3));
			h_sw_capture_wstrb: assert (!(h_sw_mem_phase && wrapper.uut.dbg_mem_valid &&
				wrapper.uut.dbg_mem_ready && !wrapper.uut.dbg_mem_instr) ||
				wrapper.uut.dbg_mem_wstrb == 4'b1111);

			h_sw_capture_rs1_zero: assert (!(h_sw_mem_phase &&
				wrapper.uut.dbg_insn_opcode[19:15] == 5'd0) ||
				wrapper.uut.dbg_rs1val == 32'd0);
			h_sw_capture_rs1_valid: assert (!(h_sw_mem_phase &&
				wrapper.uut.dbg_insn_opcode[19:15] != 5'd0) ||
				wrapper.uut.dbg_rs1val_valid);
			h_st_rs1_zero: assert (!(h_st_seen && h_st_insn[19:15] == 5'd0) ||
				h_st_rs1 == 32'd0);

			h_st_addr_match: assert (!h_st_seen ||
				h_st_addr == ((h_st_rs1 + h_st_imm) & ~32'd3));
			h_st_insn_stable: assert (!(h_st_seen && !rvfi_valid) ||
				wrapper.uut.dbg_insn_opcode == h_st_insn);
			h_st_rs1_stable: assert (!(h_st_seen && !rvfi_valid) ||
				(wrapper.uut.dbg_rs1val_valid && wrapper.uut.dbg_rs1val == h_st_rs1));
			h_st_rs2_stable: assert (!(h_st_seen && !rvfi_valid) ||
				(wrapper.uut.dbg_rs2val_valid && wrapper.uut.dbg_rs2val == h_st_rs2));
			h_st_rvfi_addr: assert (!h_st_seen || rvfi_mem_addr == h_st_addr);
			h_sw_seen_at_fetch: assert (!(wrapper.uut.cpu_state == 8'b01000000 &&
				h_is_sw && wrapper.uut.dbg_valid_insn) || h_st_seen);

			h_st_retire: assert (!(checker_inst.spec_valid && !checker_inst.spec_trap) ||
				(h_st_seen &&
				 rvfi_mem_addr == h_st_addr &&
				 rvfi_insn == h_st_insn &&
				 rvfi_rs1_rdata == h_st_rs1));
		end
	end
/// Helper Assertion End


endmodule
