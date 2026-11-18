`default_nettype none
module testbench(input clock, input reset);
	reg pcpi_valid;
	reg [31:0] pcpi_insn, pcpi_rs1, pcpi_rs2;
	wire [31:0] pcpi_rd;
	wire pcpi_wr, pcpi_wait, pcpi_ready;

	picorv32_pcpi_div dut (
		.clk(clock), .resetn(!reset),
		.pcpi_valid(pcpi_valid), .pcpi_insn(pcpi_insn),
		.pcpi_rs1(pcpi_rs1), .pcpi_rs2(pcpi_rs2),
		.pcpi_wr(pcpi_wr), .pcpi_rd(pcpi_rd),
		.pcpi_wait(pcpi_wait), .pcpi_ready(pcpi_ready));

	wire h_start = dut.start;
	wire h_loop  = dut.running && (dut.quotient_msk != 0);

	reg [31:0] h_N;
	reg [31:0] h_M; // |rs1| at start (pinned to the RTL by h_*_start_dividend)
	reg [5:0]  h_k;
	always @(posedge clock) begin
		if (reset) begin h_N <= 0; h_k <= 0; end
		else if (h_start) begin
			h_N <= ((dut.instr_div || dut.instr_rem) && pcpi_rs2[31]) ? -pcpi_rs2 : pcpi_rs2;
			h_k <= 6'd31;
		end else if (h_loop)
			h_k <= h_k - 1;
	end

	always @(posedge clock) begin
		if (reset) h_M <= 32'd0;
		else if (h_start)
			h_M <= ((dut.instr_div || dut.instr_rem) && pcpi_rs1[31]) ? -pcpi_rs1 : pcpi_rs1;
	end

	always @(posedge clock) begin
		if (!reset) begin
			// step 1: loop-state correspondence (active-loop phase)
			if (h_loop) begin
				h_msk_shift: assert(dut.quotient_msk == (32'd1 << h_k));
				h_div_shift: assert(dut.divisor == ({31'd0, h_N} << h_k));
			end
			// step 2: loop-update correspondence (one-step, previous cycle was a loop step)
			if ($past(!reset) && $past(h_loop) && !$past(h_start)) begin
				h_div_update:      assert(dut.divisor == ($past(dut.divisor) >> 1));
				h_msk_update:      assert(dut.quotient_msk == ($past(dut.quotient_msk) >> 1));
				h_k_update:        assert(h_k == ($past(h_k) - 6'd1));
				h_dividend_update: assert(dut.dividend == ($past(dut.divisor) <= $past(dut.dividend)
				                                           ? $past(dut.dividend) - $past(dut.divisor)
				                                           : $past(dut.dividend)));
				h_quotient_update: assert(dut.quotient == ($past(dut.quotient) | ($past(dut.divisor) <= $past(dut.dividend)
				                                           ? $past(dut.quotient_msk) : 32'd0)));
			end
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			// step 3: loop invariant for msk>1 (divisor even via the manifold)
			if (h_loop && dut.quotient_msk != 32'd1 && dut.divisor != 0)
				h_inv: assert({32'd0, dut.dividend} < ({1'b0, dut.divisor} << 1));
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			// step 4a: inherited last premise at msk==1 (divisor == N): d < 2N
			if (h_loop && dut.quotient_msk == 32'd1 && dut.divisor != 0)
				h_last_premise: assert({32'd0, dut.dividend} < ({1'b0, dut.divisor} << 1));
			// step 4b: terminal ordering at the finish cycle (running && msk==0)
			if ($past(!reset) && dut.running && dut.quotient_msk == 0 && h_N != 0)
				h_term: assert(dut.dividend < h_N);
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			// div entry instantiation: the RTL's registers are the abstract
			// initial state (M = |rs1|, N = |rs2|)
			if ($past(!reset) && $past(h_start)) begin
				h_div_start_dividend: assert(dut.dividend == h_M);
				h_div_start_quotient: assert(dut.quotient == 32'd0);
				h_div_start_msk:      assert(dut.quotient_msk == (32'd1 << 31));
				h_div_start_divisor:  assert(dut.divisor == ({31'd0, h_N} << 31));
				h_div_start_outsign:  assert(dut.outsign ==
					(($past(dut.instr_div)
					    && ($past(pcpi_rs1[31]) != $past(pcpi_rs2[31]))
					    && ($past(pcpi_rs2) != 32'd0))
					 || ($past(dut.instr_rem) && $past(pcpi_rs1[31]))));
			end
			// the dividend is not updated at the finish edge
			if ($past(!reset) && $past(dut.running) && $past(dut.quotient_msk) == 32'd0
			    && !$past(h_start))
				h_div_finish_stable: assert(dut.dividend == $past(dut.dividend));
			// the value written back at the finish edge (picorv32.sv:2476-2479):
			// the RTL selects quotient-vs-dividend by the *current* decode
			if ($past(!reset) && $past(dut.running) && $past(dut.quotient_msk) == 32'd0
			    && !$past(h_start)) begin
				if ($past(dut.instr_div) || $past(dut.instr_divu))
					h_finish_value_div: assert(pcpi_rd ==
						($past(dut.outsign) ? -$past(dut.quotient) : $past(dut.quotient)));
				else
					h_finish_value_rem: assert(pcpi_rd ==
						($past(dut.outsign) ? -$past(dut.dividend) : $past(dut.dividend)));
			end
		end
	end
endmodule
