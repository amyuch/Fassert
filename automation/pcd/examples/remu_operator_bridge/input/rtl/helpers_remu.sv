/// Helper Assertion Begin
	wire h_is_remu = (wrapper.uut.dbg_insn_opcode[6:0] == 7'b0110011) &&
	                 (wrapper.uut.dbg_insn_opcode[14:12] == 3'b111) &&
	                 (wrapper.uut.dbg_insn_opcode[31:25] == 7'b0000001);

	// Divider control/data-path observation (unsigned remainder).
	wire h_remu_start_i = wrapper.uut.pcd_div.pcpi_div.start &&
	                     wrapper.uut.pcd_div.pcpi_div.instr_remu;
	reg  h_remu_active;
	reg [31:0] h_remu_m;
	reg [31:0] h_remu_n;
	reg [5:0]  h_remu_k;
	wire h_remu_loop = wrapper.uut.pcd_div.pcpi_div.running &&
	                  (wrapper.uut.pcd_div.pcpi_div.quotient_msk != 0) && h_remu_active;

	always @(posedge clock) begin
		if (reset) begin
			h_remu_m <= 32'd0;
			h_remu_n <= 32'd0;
			h_remu_k <= 6'd0;
			h_remu_active <= 1'b0;
		end else if (h_remu_start_i) begin
			h_remu_m <= wrapper.uut.pcpi_rs1;
			h_remu_n <= wrapper.uut.pcpi_rs2;
			h_remu_k <= 6'd31;
			h_remu_active <= 1'b1;
		end else begin
			if (h_remu_loop) h_remu_k <= h_remu_k - 6'd1;
			if (!wrapper.uut.pcd_div.pcpi_div.running ||
			    !wrapper.uut.pcd_div.pcpi_div.instr_remu)
				h_remu_active <= 1'b0;
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			// Entry facts.
			if ($past(!reset) && $past(h_remu_start_i)) begin
				h_remu_start_d: assert(wrapper.uut.pcd_div.pcpi_div.dividend == h_remu_m);
				h_remu_start_q: assert(wrapper.uut.pcd_div.pcpi_div.quotient == 32'd0);
				h_remu_start_msk: assert(wrapper.uut.pcd_div.pcpi_div.quotient_msk == (32'd1 << 31));
				h_remu_start_divisor: assert(wrapper.uut.pcd_div.pcpi_div.divisor == {31'd0, h_remu_n} << 31);
				h_remu_start_sign: assert(wrapper.uut.pcd_div.pcpi_div.outsign == 1'b0);
			end

			// Loop facts.
			if (!reset && h_remu_loop) begin
				h_remu_div_k: assert(wrapper.uut.pcd_div.pcpi_div.divisor == ({31'd0, h_remu_n} << h_remu_k));
				h_remu_msk_k: assert(wrapper.uut.pcd_div.pcpi_div.quotient_msk == (32'd1 << h_remu_k));
			end
			if ($past(!reset) && $past(h_remu_loop) && !$past(wrapper.uut.pcd_div.pcpi_div.start)) begin
				h_remu_step_d: assert(wrapper.uut.pcd_div.pcpi_div.dividend ==
					(($past(wrapper.uut.pcd_div.pcpi_div.divisor) <= $past(wrapper.uut.pcd_div.pcpi_div.dividend))
					 ? $past(wrapper.uut.pcd_div.pcpi_div.dividend) - $past(wrapper.uut.pcd_div.pcpi_div.divisor)
					 : $past(wrapper.uut.pcd_div.pcpi_div.dividend)));
				h_remu_step_q: assert(wrapper.uut.pcd_div.pcpi_div.quotient ==
					(($past(wrapper.uut.pcd_div.pcpi_div.divisor) <= $past(wrapper.uut.pcd_div.pcpi_div.dividend))
					 ? ($past(wrapper.uut.pcd_div.pcpi_div.quotient) | $past(wrapper.uut.pcd_div.pcpi_div.quotient_msk))
					 : $past(wrapper.uut.pcd_div.pcpi_div.quotient)));
				h_remu_step_msk: assert(wrapper.uut.pcd_div.pcpi_div.quotient_msk ==
					($past(wrapper.uut.pcd_div.pcpi_div.quotient_msk) >> 1));
			end

			// Result and writeback links.
			if (!reset && wrapper.uut.pcpi_div_ready && !wrapper.uut.pcpi_mul_ready)
				h_remu_mux: assert(wrapper.uut.pcpi_int_rd == wrapper.uut.pcpi_div_rd);
			if ($past(!reset) && $past(wrapper.uut.cpu_state == 8'b00100000 &&
			    wrapper.uut.instr_trap && wrapper.uut.pcpi_div_ready))
				h_remu_capture: assert(wrapper.uut.reg_out == $past(wrapper.uut.pcpi_int_rd));
			if (!reset && wrapper.uut.cpu_state == 8'b01000000 && wrapper.uut.latched_store &&
			    !wrapper.uut.latched_branch && !wrapper.uut.latched_stalu)
				h_remu_wb: assert(wrapper.uut.cpuregs_wrdata == wrapper.uut.reg_out);
			if ($past(!reset) && $past(wrapper.uut.cpuregs_write) &&
			    !$past(wrapper.uut.irq_state) && $past(h_is_remu))
				h_remu_rvfi_wdata: assert(wrapper.uut.rvfi_rd_wdata ==
					($past(wrapper.uut.latched_rd) ? $past(wrapper.uut.cpuregs_wrdata) : 32'd0));
			if (!reset && checker_inst.spec_valid)
				h_remu_rvfi_rd: assert(rvfi_rd_addr == rvfi_insn[11:7]);

			// Destination-address link used by the RD induction.
			h_commit_rd: assert (!(wrapper.uut.cpuregs_write && h_is_remu) ||
				wrapper.uut.latched_rd == wrapper.uut.dbg_insn_opcode[11:7]);

			if ($past(!reset) && wrapper.uut.pcpi_div_ready &&
			    h_remu_active && $past(wrapper.uut.pcd_div.pcpi_div.instr_remu))
				h_remu_finish: assert(wrapper.uut.pcpi_div_rd == $past(wrapper.uut.pcd_div.pcpi_div.dividend));
		end
	end
/// Helper Assertion End
