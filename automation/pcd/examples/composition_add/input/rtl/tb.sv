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
	// Fresh ADD strengthening, built from the same launch/retire boundary idea
	// as the ADDI case but with the R-type operand pair.
	wire h_add_dut = (wrapper.uut.dbg_insn_opcode[6:0] == 7'b0110011) &&
	                 (wrapper.uut.dbg_insn_opcode[14:12] == 3'b000) &&
	                 (wrapper.uut.dbg_insn_opcode[31:25] == 7'b0000000);
	wire h_add_rvfi = (rvfi_insn[6:0] == 7'b0110011) &&
	                  (rvfi_insn[14:12] == 3'b000) &&
	                  (rvfi_insn[31:25] == 7'b0000000);

	reg        h_add_wb_hit;
	reg [31:0] h_add_wb_opcode;
	reg [31:0] h_add_wb_rs1;
	reg [31:0] h_add_wb_rs2;
	reg [31:0] h_add_wb_data;
	reg [4:0]  h_add_wb_rd;

	always @(posedge clock) begin
		if (reset) begin
			h_add_wb_hit    <= 1'b0;
			h_add_wb_opcode <= 32'd0;
			h_add_wb_rs1    <= 32'd0;
			h_add_wb_rs2    <= 32'd0;
			h_add_wb_data   <= 32'd0;
			h_add_wb_rd     <= 5'd0;
		end else begin
			if (rvfi_valid) h_add_wb_hit <= 1'b0;
			if (wrapper.uut.cpuregs_write && h_add_dut) begin
				h_add_wb_hit    <= 1'b1;
				h_add_wb_opcode <= wrapper.uut.dbg_insn_opcode;
				h_add_wb_rs1    <= wrapper.uut.reg_op1;
				h_add_wb_rs2    <= wrapper.uut.reg_op2;
				h_add_wb_data   <= wrapper.uut.cpuregs_wrdata;
				h_add_wb_rd     <= wrapper.uut.latched_rd;
			end
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			h_add_rvfi_insn: assert (rvfi_insn == $past(wrapper.uut.dbg_insn_opcode));
			h_add_rvfi_pc: assert (rvfi_pc_rdata == $past(wrapper.uut.dbg_insn_addr));
			h_add_rvfi_valid: assert (rvfi_valid == $past((!reset) &&
				(wrapper.uut.launch_next_insn || wrapper.uut.trap) &&
				wrapper.uut.dbg_valid_insn));
			h_add_rvfi_rs1: assert (!(rvfi_valid && h_add_rvfi) ||
				rvfi_rs1_rdata == $past(wrapper.uut.dbg_rs1val_valid ?
					wrapper.uut.dbg_rs1val : 32'd0));
			h_add_rvfi_rs2: assert (!(rvfi_valid && h_add_rvfi) ||
				rvfi_rs2_rdata == $past(wrapper.uut.dbg_rs2val_valid ?
					wrapper.uut.dbg_rs2val : 32'd0));
			h_add_rvfi_rd_data: assert (!(rvfi_valid && h_add_rvfi) ||
				rvfi_rd_wdata == ($past(reset) ? 32'd0 :
					($past(wrapper.uut.cpuregs_write) && !$past(wrapper.uut.irq_state)) ?
						($past(wrapper.uut.latched_rd) ? $past(wrapper.uut.cpuregs_wrdata) : 32'd0) :
					($past(rvfi_valid) ? 32'd0 : $past(rvfi_rd_wdata))));
			h_add_rvfi_rd_addr: assert (!(rvfi_valid && h_add_rvfi) ||
				rvfi_rd_addr == ($past(reset) ? 5'd0 :
					($past(wrapper.uut.cpuregs_write) && !$past(wrapper.uut.irq_state)) ?
						$past(wrapper.uut.latched_rd) :
					($past(rvfi_valid) ? 5'd0 : $past(rvfi_rd_addr))));

			h_add_no_irq: assert (!(rvfi_valid && h_add_rvfi) || !wrapper.uut.dbg_irq_call);
			h_add_no_trap: assert (!(rvfi_valid && h_add_rvfi) || !wrapper.uut.trap);

			h_add_commit_kind: assert (!(wrapper.uut.cpuregs_write && h_add_dut) ||
				(wrapper.uut.latched_store && wrapper.uut.latched_stalu &&
				 !wrapper.uut.latched_branch && !wrapper.uut.irq_state));
			h_add_commit_sum: assert (!(wrapper.uut.cpuregs_write && h_add_dut) ||
				wrapper.uut.cpuregs_wrdata == wrapper.uut.reg_op1 + wrapper.uut.reg_op2);
			h_add_commit_rd: assert (!(wrapper.uut.cpuregs_write && h_add_dut) ||
				wrapper.uut.latched_rd == wrapper.uut.dbg_insn_opcode[11:7]);
			h_add_commit_rs1: assert (!(wrapper.uut.cpuregs_write && h_add_dut &&
				wrapper.uut.dbg_rs1val_valid) ||
				wrapper.uut.dbg_rs1val == wrapper.uut.reg_op1);
			h_add_commit_rs2: assert (!(wrapper.uut.cpuregs_write && h_add_dut &&
				wrapper.uut.dbg_rs2val_valid) ||
				wrapper.uut.dbg_rs2val == wrapper.uut.reg_op2);

			h_add_launch_opcode: assert (!(wrapper.uut.launch_next_insn &&
				wrapper.uut.dbg_valid_insn && h_add_dut) ||
				wrapper.uut.cpuregs_write ||
				(h_add_wb_hit && wrapper.uut.dbg_insn_opcode == h_add_wb_opcode));
			h_add_launch_operands: assert (!(wrapper.uut.launch_next_insn &&
				wrapper.uut.dbg_valid_insn && h_add_dut) ||
				(wrapper.uut.cpuregs_write ?
					(wrapper.uut.dbg_rs1val_valid && wrapper.uut.dbg_rs2val_valid &&
					 wrapper.uut.dbg_rs1val == wrapper.uut.reg_op1 &&
					 wrapper.uut.dbg_rs2val == wrapper.uut.reg_op2) :
					(h_add_wb_hit && wrapper.uut.dbg_rs1val_valid &&
					 wrapper.uut.dbg_rs2val_valid &&
					 wrapper.uut.dbg_rs1val == h_add_wb_rs1 &&
					 wrapper.uut.dbg_rs2val == h_add_wb_rs2)));
			h_add_launch_rd_data: assert (!(wrapper.uut.launch_next_insn &&
				wrapper.uut.dbg_valid_insn && h_add_dut) ||
				wrapper.uut.cpuregs_write ||
				(h_add_wb_hit && rvfi_rd_wdata ==
					(h_add_wb_rd ? h_add_wb_data : 32'd0)));
			h_add_launch_rd: assert (!(wrapper.uut.launch_next_insn &&
				wrapper.uut.dbg_valid_insn && h_add_dut) ||
				wrapper.uut.latched_rd == wrapper.uut.dbg_insn_opcode[11:7]);
			h_add_launch_rs1_zero: assert (!(wrapper.uut.launch_next_insn &&
				wrapper.uut.dbg_valid_insn && h_add_dut) ||
				wrapper.uut.dbg_insn_opcode[19:15] != 5'd0 ||
				wrapper.uut.dbg_rs1val == 32'd0);
			h_add_launch_rs2_zero: assert (!(wrapper.uut.launch_next_insn &&
				wrapper.uut.dbg_valid_insn && h_add_dut) ||
				wrapper.uut.dbg_insn_opcode[24:20] != 5'd0 ||
				wrapper.uut.dbg_rs2val == 32'd0);

			h_add_wb_sum: assert (!h_add_wb_hit ||
				h_add_wb_data == h_add_wb_rs1 + h_add_wb_rs2);
			h_add_wb_retire: assert (!(rvfi_valid && h_add_rvfi) ||
				(h_add_wb_hit &&
				 h_add_wb_rd == rvfi_insn[11:7] &&
				 rvfi_rd_wdata == (h_add_wb_rd ? h_add_wb_data : 32'd0) &&
				 rvfi_rs1_rdata == h_add_wb_rs1 &&
				 rvfi_rs2_rdata == h_add_wb_rs2));
			h_add_pc_step: assert (!(rvfi_valid && h_add_rvfi) ||
				wrapper.uut.dbg_insn_addr == rvfi_pc_rdata + 32'd4);
		end
	end
/// Helper Assertion End


endmodule
