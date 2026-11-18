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
	wire h_is_jal = (wrapper.uut.dbg_insn_opcode[6:0] == 7'b1101111);
	wire h_rvfi_jal = (rvfi_insn[6:0] == 7'b1101111);
	wire [31:0] h_imm = $signed({rvfi_insn[31], rvfi_insn[19:12], rvfi_insn[20], rvfi_insn[30:21], 1'b0});

	reg        h_jal_seen;
	reg [31:0] h_jal_pc;
	reg [31:0] h_jal_imm;
	reg [31:0] h_jal_opcode;
	reg [31:0] h_jal_target;

	always @(posedge clock) begin
		if (reset) begin
			h_jal_seen   <= 1'b0;
			h_jal_pc     <= 32'd0;
			h_jal_imm    <= 32'd0;
			h_jal_opcode <= 32'd0;
			h_jal_target <= 32'd0;
		end else begin
			if (rvfi_valid)
				h_jal_seen <= 1'b0;
			if (wrapper.uut.launch_next_insn && wrapper.uut.dbg_valid_insn && h_is_jal) begin
				h_jal_seen   <= 1'b1;
				h_jal_pc     <= wrapper.uut.dbg_insn_addr;
				h_jal_imm    <= wrapper.uut.dbg_insn_imm;
				h_jal_opcode <= wrapper.uut.dbg_insn_opcode;
				h_jal_target <= wrapper.uut.next_pc;
			end
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			h_rvfi_insn_eq: assert (rvfi_insn == $past(wrapper.uut.dbg_insn_opcode));
			h_rvfi_pc_rdata_eq: assert (rvfi_pc_rdata == $past(wrapper.uut.dbg_insn_addr));
			h_rvfi_valid_eq: assert (rvfi_valid == $past((!reset) && (wrapper.uut.launch_next_insn || wrapper.uut.trap) && wrapper.uut.dbg_valid_insn));
			h_no_irq_on_jal: assert (!(rvfi_valid && check && h_rvfi_jal) || !wrapper.uut.dbg_irq_call);
			h_no_trap_on_jal: assert (!(rvfi_valid && check && h_rvfi_jal) || !wrapper.uut.trap);

			h_jal_seen_ret: assert (!(rvfi_valid && check && h_rvfi_jal) || h_jal_seen);
			h_jal_pc_ret: assert (!(rvfi_valid && check && h_rvfi_jal) || rvfi_pc_rdata == h_jal_pc);
			h_jal_opcode_ret: assert (!(rvfi_valid && check && h_rvfi_jal) || rvfi_insn == h_jal_opcode);
			h_jal_imm_ret: assert (!(rvfi_valid && check && h_rvfi_jal) || h_imm == h_jal_imm);
			h_jal_target_ret: assert (!(rvfi_valid && check && h_rvfi_jal) || wrapper.uut.dbg_insn_addr == h_jal_target);
			h_launch_target: assert (!(wrapper.uut.launch_next_insn && wrapper.uut.dbg_valid_insn && h_is_jal) ||
				wrapper.uut.next_pc == ((wrapper.uut.dbg_insn_addr + wrapper.uut.dbg_insn_imm) & ~32'd1));

			h_pc_next: assert (!(rvfi_valid && check && h_rvfi_jal) ||
				wrapper.uut.dbg_insn_addr == (h_jal_pc + h_jal_imm));
			h_rvfi_pc_eq: assert (!(rvfi_valid && check && h_rvfi_jal) ||
				rvfi_pc_wdata == wrapper.uut.dbg_insn_addr);
			h_spec_pc_eq: assert (!(rvfi_valid && check && h_rvfi_jal) ||
				checker_inst.spec_pc_wdata == (h_jal_pc + h_jal_imm));
			h_pc_official: assert (!(rvfi_valid && check && h_rvfi_jal) ||
				checker_inst.spec_pc_wdata == rvfi_pc_wdata);
		end
	end
/// Helper Assertion End
endmodule
