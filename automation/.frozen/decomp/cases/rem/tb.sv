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
	wire h_is_rem = (wrapper.uut.dbg_insn_opcode[31:25] == 7'b0000001)
	             && (wrapper.uut.dbg_insn_opcode[14:12] == 3'b110)
	             && (wrapper.uut.dbg_insn_opcode[6:0] == 7'b0110011);
	always @(posedge clock) begin
		if (!reset) begin
			if (wrapper.uut.pcpi_div_ready && !wrapper.uut.pcpi_mul_ready)
				h_rem_mux: assert(wrapper.uut.pcpi_int_rd == wrapper.uut.pcpi_div_rd);
			if ($past(!reset) && $past(wrapper.uut.cpu_state == 8'b00100000 && wrapper.uut.instr_trap && wrapper.uut.pcpi_div_ready))
				h_rem_ready_capture: assert(wrapper.uut.reg_out == $past(wrapper.uut.pcpi_int_rd));
			if (wrapper.uut.cpu_state == 8'b01000000 && wrapper.uut.latched_store && !wrapper.uut.latched_branch && !wrapper.uut.latched_stalu)
				h_rem_wb_mux: assert(wrapper.uut.cpuregs_wrdata == wrapper.uut.reg_out);
			if (wrapper.uut.cpu_state == 8'b01000000 && wrapper.uut.latched_store && !wrapper.uut.latched_branch && h_is_rem)
				h_rem_wb_not_alu: assert(!wrapper.uut.latched_stalu);
			if ($past(!reset) && $past(wrapper.uut.cpuregs_write) && !$past(wrapper.uut.irq_state) && $past(h_is_rem))
				h_rem_rvfi_link: assert(wrapper.uut.rvfi_rd_wdata == ($past(wrapper.uut.latched_rd) ? $past(wrapper.uut.cpuregs_wrdata) : 32'd0));
		end
	end

	// --- reused links for REM (S24/S26/S28 analogues) ---
	always @(posedge clock) begin
		if (!reset) begin
			if (checker_inst.spec_valid)
				h_rem_dest: assert(rvfi_rd_addr == rvfi_insn[11:7]);
			if ($past(!reset) && wrapper.uut.rvfi_valid && $past(h_is_rem)) begin
				h_rem_rs1: assert(wrapper.uut.rvfi_rs1_rdata == $past(wrapper.uut.pcpi_rs1));
				h_rem_rs2: assert(wrapper.uut.rvfi_rs2_rdata == $past(wrapper.uut.pcpi_rs2));
			end
			// REM finish mux (dividend path) at the ready cycle, finish-edge values
			if ($past(!reset) && wrapper.uut.pcpi_div_ready && $past(wrapper.uut.genblk2.pcpi_div.instr_rem))
				h_rem_finish: assert(wrapper.uut.pcpi_div_rd == ($past(wrapper.uut.genblk2.pcpi_div.outsign)
					? -$past(wrapper.uut.genblk2.pcpi_div.dividend)
					:  $past(wrapper.uut.genblk2.pcpi_div.dividend)));
		end
	end

	// --- reused S30 loop/terminal facts (divider, op-independent) ---
	wire h_start = wrapper.uut.genblk2.pcpi_div.start;
	wire h_loop  = wrapper.uut.genblk2.pcpi_div.running && (wrapper.uut.genblk2.pcpi_div.quotient_msk != 0);
	reg [31:0] h_N; reg [5:0] h_k;
	always @(posedge clock) begin
		if (reset) begin h_N <= 0; h_k <= 0; end
		else if (h_start) begin
			h_N <= ((wrapper.uut.genblk2.pcpi_div.instr_div || wrapper.uut.genblk2.pcpi_div.instr_rem) && wrapper.uut.genblk2.pcpi_div.pcpi_rs2[31]) ? -wrapper.uut.genblk2.pcpi_div.pcpi_rs2 : wrapper.uut.genblk2.pcpi_div.pcpi_rs2;
			h_k <= 6'd31;
		end else if (h_loop) h_k <= h_k - 6'd1;
	end
	always @(posedge clock) begin
		if (!reset) begin
			if (h_loop) begin
				h_msk_shift: assert(wrapper.uut.genblk2.pcpi_div.quotient_msk == (32'd1 << h_k));
				h_div_shift: assert(wrapper.uut.genblk2.pcpi_div.divisor == ({31'd0, h_N} << h_k));
			end
			if ($past(!reset) && $past(h_loop) && !$past(h_start)) begin
				h_div_update:      assert(wrapper.uut.genblk2.pcpi_div.divisor == ($past(wrapper.uut.genblk2.pcpi_div.divisor) >> 1));
				h_msk_update:      assert(wrapper.uut.genblk2.pcpi_div.quotient_msk == ($past(wrapper.uut.genblk2.pcpi_div.quotient_msk) >> 1));
				h_k_update:        assert(h_k == ($past(h_k) - 6'd1));
				h_dividend_update: assert(wrapper.uut.genblk2.pcpi_div.dividend == ($past(wrapper.uut.genblk2.pcpi_div.divisor) <= $past(wrapper.uut.genblk2.pcpi_div.dividend)
				                                           ? $past(wrapper.uut.genblk2.pcpi_div.dividend) - $past(wrapper.uut.genblk2.pcpi_div.divisor) : $past(wrapper.uut.genblk2.pcpi_div.dividend)));
				h_quotient_update: assert(wrapper.uut.genblk2.pcpi_div.quotient == ($past(wrapper.uut.genblk2.pcpi_div.quotient) | ($past(wrapper.uut.genblk2.pcpi_div.divisor) <= $past(wrapper.uut.genblk2.pcpi_div.dividend)
				                                           ? $past(wrapper.uut.genblk2.pcpi_div.quotient_msk) : 32'd0)));
			end
			if (h_loop && wrapper.uut.genblk2.pcpi_div.quotient_msk != 32'd1 && wrapper.uut.genblk2.pcpi_div.divisor != 0)
				h_inv: assert({32'd0, wrapper.uut.genblk2.pcpi_div.dividend} < ({1'b0, wrapper.uut.genblk2.pcpi_div.divisor} << 1));
			if (h_loop && wrapper.uut.genblk2.pcpi_div.quotient_msk == 32'd1 && wrapper.uut.genblk2.pcpi_div.divisor != 0)
				h_last_premise: assert({32'd0, wrapper.uut.genblk2.pcpi_div.dividend} < ({1'b0, wrapper.uut.genblk2.pcpi_div.divisor} << 1));
			if ($past(!reset) && wrapper.uut.genblk2.pcpi_div.running && wrapper.uut.genblk2.pcpi_div.quotient_msk == 0 && h_N != 0)
				h_term: assert(wrapper.uut.genblk2.pcpi_div.dividend < h_N);
			// PC boundary/stability (S26 structure)
			if (wrapper.uut.cpu_state == 8'b00100000 && wrapper.uut.instr_trap && h_is_rem)
				h_rem_pc_rel: assert(wrapper.uut.next_pc == (wrapper.uut.dbg_insn_addr + 32'd4));
			if ($past(!reset) && $past(wrapper.uut.cpu_state == 8'b00100000 && wrapper.uut.instr_trap && h_is_rem)
			    && wrapper.uut.cpu_state == 8'b00100000 && wrapper.uut.instr_trap && h_is_rem) begin
				h_rem_next_pc_stable: assert(wrapper.uut.next_pc == $past(wrapper.uut.next_pc));
				h_rem_dbg_addr_stable: assert(wrapper.uut.dbg_insn_addr == $past(wrapper.uut.dbg_insn_addr));
			end
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			// REM is the divider; the MUL core must not claim readiness
			if (wrapper.uut.cpu_state == 8'b00100000 && wrapper.uut.instr_trap && h_is_rem)
				h_rem_mul_not_ready: assert(!wrapper.uut.pcpi_mul_ready);
		end
	end

	// --- entry values, RTL<->abstract value interface, sign link ---
	reg [31:0] h_M; // |rs1| at start (pinned to the RTL by h_rem_start_dividend)
	always @(posedge clock) begin
		if (reset) h_M <= 32'd0;
		else if (h_start)
			h_M <= ((wrapper.uut.genblk2.pcpi_div.instr_div || wrapper.uut.genblk2.pcpi_div.instr_rem)
			        && wrapper.uut.pcpi_rs1[31]) ? -wrapper.uut.pcpi_rs1 : wrapper.uut.pcpi_rs1;
	end

	always @(posedge clock) begin
		if (!reset) begin
			if ($past(!reset) && $past(h_start)) begin
				h_rem_start_dividend: assert(wrapper.uut.genblk2.pcpi_div.dividend == h_M);
				h_rem_start_quotient: assert(wrapper.uut.genblk2.pcpi_div.quotient == 32'd0);
				h_rem_start_msk:      assert(wrapper.uut.genblk2.pcpi_div.quotient_msk == (32'd1 << 31));
				h_rem_start_divisor:  assert(wrapper.uut.genblk2.pcpi_div.divisor == ({31'd0, h_N} << 31));
				h_rem_start_outsign:  assert(wrapper.uut.genblk2.pcpi_div.outsign ==
					(($past(wrapper.uut.genblk2.pcpi_div.instr_div)
					    && ($past(wrapper.uut.pcpi_rs1[31]) != $past(wrapper.uut.pcpi_rs2[31]))
					    && ($past(wrapper.uut.pcpi_rs2) != 32'd0))
					 || ($past(wrapper.uut.genblk2.pcpi_div.instr_rem) && $past(wrapper.uut.pcpi_rs1[31]))));
			end
			// the dividend is not updated at the finish edge (cycle alignment of
			// the finish mux value and the terminal fact)
			if ($past(!reset) && $past(wrapper.uut.genblk2.pcpi_div.running)
			    && $past(wrapper.uut.genblk2.pcpi_div.quotient_msk) == 32'd0
			    && !$past(h_start))
				h_rem_finish_stable: assert(wrapper.uut.genblk2.pcpi_div.dividend == $past(wrapper.uut.genblk2.pcpi_div.dividend));
		end
	end
/// Helper Assertion End
endmodule
