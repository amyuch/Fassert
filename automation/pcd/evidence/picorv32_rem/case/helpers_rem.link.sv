// PCD case-local helper assertions for the REM control/data path.
//
// These are obligations, not assumptions: the proof graph must discharge every
// named assertion before it may use the corresponding guarantee.  The names are
// deliberately local to this case and are never imported from another tree.

	wire p_rem_is_rem =
		(wrapper.uut.dbg_insn_opcode[31:25] == 7'b0000001) &&
		(wrapper.uut.dbg_insn_opcode[14:12] == 3'b110) &&
		(wrapper.uut.dbg_insn_opcode[6:0] == 7'b0110011);

	wire p_rem_start = wrapper.uut.pcd_div.pcpi_div.start;
	wire p_rem_start_i = p_rem_start && wrapper.uut.pcd_div.pcpi_div.instr_rem;
	reg  p_rem_active;

	reg [31:0] p_rem_m;
	reg [31:0] p_rem_n;
	reg [5:0]  p_rem_k;
	reg [63:0] p_rem_prod;
	reg [31:0] p_rem_qsum;

	wire p_rem_loop = wrapper.uut.pcd_div.pcpi_div.running &&
	                  (wrapper.uut.pcd_div.pcpi_div.quotient_msk != 0) && p_rem_active;
	wire p_rem_arith = wrapper.uut.pcd_div.pcpi_div.running && p_rem_active;


	// ---- retirement / writeback link helpers --------------------------------
	// These mirror the MUL proof's seen/writeback-word control facts.  The
	// divider result is snapshotted at the divider finish event itself, so the
	// snapshot is established by construction rather than by trusting an
	// arbitrary ready state.
	wire p_rem_rvfi_rem =
		(rvfi_insn[31:25] == 7'b0000001) &&
		(rvfi_insn[14:12] == 3'b110) &&
		(rvfi_insn[6:0] == 7'b0110011);
	wire p_rem_retire = rvfi_valid && p_rem_rvfi_rem;
	wire p_rem_wb_sel = wrapper.uut.cpuregs_write && p_rem_is_rem;
	wire p_rem_done = wrapper.uut.pcd_div.pcpi_div.running && p_rem_active &&
		(wrapper.uut.pcd_div.pcpi_div.quotient_msk == 32'd0) &&
		wrapper.uut.pcd_div.pcpi_div.instr_rem;

	reg [31:0] p_rem_start_rs1;
	reg [31:0] p_rem_start_rs2;
	reg [31:0] p_rem_finish_word;
	reg [31:0] p_rem_finish_dividend;
	reg [31:0] p_rem_finish_m;
	reg [31:0] p_rem_finish_n;
	reg        p_rem_finish_outsign;
	reg        p_rem_pcpi_valid_q;
	reg        p_rem_finish_valid;

	always @(posedge clock) begin
		if (reset) begin
			p_rem_m <= 32'd0;
			p_rem_n <= 32'd0;
			p_rem_k <= 6'd0;
			p_rem_prod <= 64'd0;
			p_rem_qsum <= 32'd0;
			p_rem_active <= 1'b0;
			p_rem_start_rs1 <= 32'd0;
			p_rem_start_rs2 <= 32'd0;
			p_rem_finish_word <= 32'd0;
			p_rem_finish_dividend <= 32'd0;
			p_rem_finish_m <= 32'd0;
			p_rem_finish_n <= 32'd0;
			p_rem_finish_outsign <= 1'b0;
			p_rem_finish_valid <= 1'b0;
			p_rem_pcpi_valid_q <= 1'b0;
		end else begin
			if (p_rem_start_i) begin
				p_rem_m <= wrapper.uut.pcpi_rs1[31] ? -wrapper.uut.pcpi_rs1 : wrapper.uut.pcpi_rs1;
				p_rem_n <= wrapper.uut.pcpi_rs2[31] ? -wrapper.uut.pcpi_rs2 : wrapper.uut.pcpi_rs2;
				p_rem_k <= 6'd31;
				p_rem_prod <= 64'd0;
				p_rem_qsum <= 32'd0;
				p_rem_active <= 1'b1;
			end else begin
				if (p_rem_loop) p_rem_k <= p_rem_k - 6'd1;
				if (p_rem_loop && (wrapper.uut.pcd_div.pcpi_div.divisor <= {32'd0, wrapper.uut.pcd_div.pcpi_div.dividend})) begin
					p_rem_prod <= p_rem_prod + {1'b0, wrapper.uut.pcd_div.pcpi_div.divisor};
					p_rem_qsum <= p_rem_qsum + wrapper.uut.pcd_div.pcpi_div.quotient_msk;
				end
				if (!wrapper.uut.pcd_div.pcpi_div.running ||
				    !wrapper.uut.pcd_div.pcpi_div.instr_rem)
					p_rem_active <= 1'b0;
			end
			if (p_rem_start_i) begin
				p_rem_start_rs1 <= wrapper.uut.pcpi_rs1;
				p_rem_start_rs2 <= wrapper.uut.pcpi_rs2;
			end
			if (p_rem_done) begin
				p_rem_finish_word <= wrapper.uut.pcd_div.pcpi_div.outsign
					? -wrapper.uut.pcd_div.pcpi_div.dividend
					:  wrapper.uut.pcd_div.pcpi_div.dividend;
				p_rem_finish_dividend <= wrapper.uut.pcd_div.pcpi_div.dividend;
				p_rem_finish_m <= p_rem_m;
				p_rem_finish_n <= p_rem_n;
				p_rem_finish_outsign <= wrapper.uut.pcd_div.pcpi_div.outsign;
				p_rem_finish_valid <= 1'b1;
			end
			if (rvfi_valid)
				p_rem_finish_valid <= 1'b0;
			p_rem_pcpi_valid_q <= wrapper.uut.pcpi_valid;
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			// The divider starts with the magnitude operands, zero quotient,
			// the top mask bit, and the scaled divisor.
			if ($past(!reset) && $past(p_rem_start_i)) begin
				p_rem_start_d: assert(wrapper.uut.pcd_div.pcpi_div.dividend == p_rem_m);
				p_rem_start_qsum: assert(p_rem_qsum == 32'd0);
				p_rem_start_prod: assert(p_rem_prod == 64'd0);
				p_rem_start_msk: assert(wrapper.uut.pcd_div.pcpi_div.quotient_msk == (32'd1 << 31));
				p_rem_start_divisor: assert(wrapper.uut.pcd_div.pcpi_div.divisor == (p_rem_n << 31));
				p_rem_start_sign: assert(wrapper.uut.pcd_div.pcpi_div.outsign ==
					$past(wrapper.uut.pcpi_rs1[31]));
			end

			// Loop scaling: at step k the divisor is N<<k and the mask is 1<<k.
			if (p_rem_loop) begin
				p_rem_div_k: assert(wrapper.uut.pcd_div.pcpi_div.divisor == (p_rem_n << p_rem_k));
				p_rem_msk_k: assert(wrapper.uut.pcd_div.pcpi_div.quotient_msk == (32'd1 << p_rem_k));
			end

			// One restoring-division step, plus the fixed shift of the mask.
			if ($past(!reset) && $past(p_rem_loop) && !$past(p_rem_start)) begin
				p_rem_step_d: assert(wrapper.uut.pcd_div.pcpi_div.dividend ==
					(($past(wrapper.uut.pcd_div.pcpi_div.divisor) <= $past(wrapper.uut.pcd_div.pcpi_div.dividend))
					 ? $past(wrapper.uut.pcd_div.pcpi_div.dividend) - $past(wrapper.uut.pcd_div.pcpi_div.divisor)
					 : $past(wrapper.uut.pcd_div.pcpi_div.dividend)));
				p_rem_step_msk: assert(wrapper.uut.pcd_div.pcpi_div.quotient_msk ==
					($past(wrapper.uut.pcd_div.pcpi_div.quotient_msk) >> 1));
			end

			// Data-path observation links.
			if (wrapper.uut.pcpi_div_ready && !wrapper.uut.pcpi_mul_ready)
				p_rem_mux: assert(wrapper.uut.pcpi_int_rd == wrapper.uut.pcpi_div_rd);

			if ($past(!reset) && $past(wrapper.uut.cpu_state == 8'b00100000 &&
			    wrapper.uut.instr_trap && wrapper.uut.pcpi_div_ready))
				p_rem_capture: assert(wrapper.uut.reg_out == $past(wrapper.uut.pcpi_int_rd));

			if (wrapper.uut.cpu_state == 8'b01000000 && wrapper.uut.latched_store &&
			    !wrapper.uut.latched_branch && !wrapper.uut.latched_stalu)
				p_rem_wb: assert(wrapper.uut.cpuregs_wrdata == wrapper.uut.reg_out);

			if ($past(!reset) && $past(wrapper.uut.cpuregs_write) &&
			    !$past(wrapper.uut.irq_state) && $past(p_rem_is_rem))
				p_rem_rvfi_wdata: assert(wrapper.uut.rvfi_rd_wdata ==
					($past(wrapper.uut.latched_rd) ? $past(wrapper.uut.cpuregs_wrdata) : 32'd0));

			if (checker_inst.spec_valid)
				p_rem_rvfi_rd: assert(rvfi_rd_addr == rvfi_insn[11:7]);

			// The divider owns the result at the REM finish edge.
			if ($past(!reset) && wrapper.uut.pcpi_div_ready &&
			    p_rem_active && $past(wrapper.uut.pcd_div.pcpi_div.instr_rem))
				p_rem_finish: assert(wrapper.uut.pcpi_div_rd ==
					($past(wrapper.uut.pcd_div.pcpi_div.outsign)
					 ? -$past(wrapper.uut.pcd_div.pcpi_div.dividend)
					 :  $past(wrapper.uut.pcd_div.pcpi_div.dividend)));
		end
	end

	// Additional arithmetic loop invariants for the development proof.  These
	// are assertions, not assumptions: the clean cill run must discharge them.
	wire [63:0] p_rem_rel_lhs =
		{32'd0, wrapper.uut.pcd_div.pcpi_div.dividend} +
		({32'd0, p_rem_n} * {32'd0, p_rem_qsum});
	wire [63:0] p_rem_rel_rhs = {32'd0, p_rem_m};
	wire [63:0] p_rem_prod_lhs =
		{32'd0, p_rem_n} * {32'd0, wrapper.uut.pcd_div.pcpi_div.quotient_msk};
	wire [63:0] p_rem_prod_rhs = {1'b0, wrapper.uut.pcd_div.pcpi_div.divisor};
	wire [63:0] p_rem_bound_lhs = {32'd0, wrapper.uut.pcd_div.pcpi_div.dividend};
	wire [63:0] p_rem_bound_rhs = {1'b0, wrapper.uut.pcd_div.pcpi_div.divisor} << 1;

	always @(posedge clock) begin
		if (!reset) begin
			if (p_rem_arith) begin
				p_rem_no_start: assert(!p_rem_start);
				p_rem_rel: assert(p_rem_rel_lhs == p_rem_rel_rhs);
				p_rem_prod_eq: assert(p_rem_prod == ({32'd0, p_rem_n} * {32'd0, p_rem_qsum}));
				p_rem_sum_eq: assert(({32'd0, wrapper.uut.pcd_div.pcpi_div.dividend} + p_rem_prod) == {32'd0, p_rem_m});
				p_rem_k_range: assert(p_rem_k <= 6'd31);
			end
			if (p_rem_loop) begin
				p_rem_prodshift: assert(p_rem_prod_lhs == p_rem_prod_rhs);
				if (p_rem_n != 32'd0)
					p_rem_bound: assert(p_rem_bound_lhs < p_rem_bound_rhs);
			end
			if (p_rem_active && wrapper.uut.pcd_div.pcpi_div.running &&
			    wrapper.uut.pcd_div.pcpi_div.quotient_msk == 32'd0 && p_rem_n != 32'd0) begin
				p_rem_done_lt: assert(wrapper.uut.pcd_div.pcpi_div.dividend < p_rem_n);
				p_rem_term_urem: assert(wrapper.uut.pcd_div.pcpi_div.dividend == (p_rem_m % p_rem_n));
			end
		end
	end

	always @(posedge clock) begin
		if (!reset) begin

			// Timeout/counter control lemmas.  These are obligations, not
			// assumptions: the control cill run must discharge every one.

			p_rem_start_mn_a: assert(!p_rem_active ||
				(p_rem_m == (p_rem_start_rs1[31] ? -p_rem_start_rs1 : p_rem_start_rs1) &&
				 p_rem_n == (p_rem_start_rs2[31] ? -p_rem_start_rs2 : p_rem_start_rs2)));
			if (p_rem_wb_sel) begin
				p_rem_wb_finish_a: assert(p_rem_finish_valid);
				p_rem_wb_word_a: assert(wrapper.uut.cpuregs_wrdata == p_rem_finish_word);
			end
			if (checker_inst.spec_valid) begin
				p_rem_ret_finish_a: assert(p_rem_finish_valid);
				p_rem_ret_word_a: assert(rvfi_rd_wdata ==
					(rvfi_rd_addr != 5'd0 ? p_rem_finish_word : 32'd0));
				p_rem_ret_value_a: assert(rvfi_rd_addr == 5'd0 ||
					p_rem_finish_word == checker_inst.spec_rd_wdata);
			end
			if (p_rem_finish_valid) begin
				p_rem_finish_word_a: assert(p_rem_finish_word ==
					(p_rem_finish_outsign ? -p_rem_finish_dividend : p_rem_finish_dividend));
			end
		end
	end

	// Retirement capture/value lemmas for the arithmetic fallback.
	always @(posedge clock) begin
		if (!reset) begin
			if (checker_inst.spec_valid) begin
				p_rem_ret_rs1_a: assert(p_rem_start_rs1 == (rvfi_insn[19:15] != 5'd0 ? rvfi_rs1_rdata : 32'd0));
				p_rem_ret_rs2_a: assert(p_rem_start_rs2 == (rvfi_insn[24:20] != 5'd0 ? rvfi_rs2_rdata : 32'd0));
			end
			if (p_rem_finish_valid) begin
				p_rem_finish_mn_a: assert(
					p_rem_finish_m == (p_rem_start_rs1[31] ? -p_rem_start_rs1 : p_rem_start_rs1) &&
					p_rem_finish_n == (p_rem_start_rs2[31] ? -p_rem_start_rs2 : p_rem_start_rs2));
				p_rem_finish_mod_a: assert(p_rem_finish_n == 0 ||
					p_rem_finish_dividend == (p_rem_finish_m % p_rem_finish_n));
				p_rem_finish_zero_a: assert(p_rem_finish_n != 0 ||
					p_rem_finish_dividend == p_rem_finish_m);
				p_rem_finish_sign_a: assert(p_rem_finish_outsign == p_rem_start_rs1[31]);
			end
		end
	end
